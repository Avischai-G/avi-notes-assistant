"""Coroner as a service. Runs on Cloud Run.

Endpoints are thin: everything interesting is in app/. The one non-obvious
piece is /api/autopsy, which streams the pipeline as it runs so the caller
watches six agents work instead of a spinner.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import fleet, limits, resume, store, watch
from app.autopsy import STAGES, perform_async
from app.findings import CAUSES, extract
from app.redact import redact
from app.traces import load

WEB = Path(__file__).parent / "web"
DATA = Path(__file__).parent / "data"

api = FastAPI(title="Coroner", description="Post-mortems for dead agent runs.")


def _caller(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else
            (request.client.host if request.client else "unknown"))


def _gate(limiter: limits.Limiter, request: Request) -> None:
    """These endpoints spend money. Refuse politely rather than quietly billing."""
    ok, wait = limiter.check(_caller(request))
    if not ok:
        raise HTTPException(429, f"Rate limited — this endpoint runs live model calls. "
                                 f"Try again in {wait}s.",
                            headers={"Retry-After": str(wait)})


def _summary(c: dict) -> dict:
    cert, ev = c.get("certificate") or {}, c.get("evidence") or {}
    return {
        "run_id": c.get("run_id"),
        "title": c.get("title"),
        "cause": cert.get("cause") or c.get("prior_cause"),
        "prior_cause": c.get("prior_cause"),
        "overruled": bool(cert.get("cause") and cert["cause"] != c.get("prior_cause")),
        "confidence": cert.get("confidence"),
        "progress": ev.get("progress", 0.0),
        "steps_planned": ev.get("steps_planned", 0),
        "silent": ev.get("silent", False),
        "revivable": (c.get("resume_plan") or {}).get("revivable", False),
        "one_liner": cert.get("plain_english", "")[:240],
    }


@api.get("/api/health")
def healthz():
    return {"ok": True, "model": os.environ.get("CORONER_MODEL", "gemini-3.5-flash")}


@api.get("/api/taxonomy")
def taxonomy():
    return {k: {"label": v[0], "meaning": v[1], "prevention": v[2]} for k, v in CAUSES.items()}


@api.get("/api/stages")
def stages():
    return [{"agent": a, "label": l, "does": d} for a, l, d in STAGES]


@api.get("/api/cases")
def cases():
    return sorted((_summary(c) for c in store.all_cases()),
                  key=lambda s: (s["cause"] or "", -(s["progress"] or 0)))


@api.get("/api/case/{run_id}")
def case(run_id: str):
    c = store.get(run_id)
    if not c:
        raise HTTPException(404, f"no case file for {run_id}")
    return c


@api.get("/api/fleet")
def fleet_report():
    """The ranked prescriptions. Precomputed — recomputing costs ~40 model calls."""
    cached = DATA / "fleet.json"
    if cached.exists():
        d = json.loads(cached.read_text())
        d["aggregate"] = fleet.aggregate(store.all_cases())   # counts stay live
        return d
    return fleet.prescribe(store.all_cases())


@api.post("/api/fleet/recompute")
def fleet_recompute(request: Request):
    """~40 model calls. Rate limited, and the result is not persisted — Cloud
    Run's filesystem is ephemeral, so the shipped fleet.json stays the source
    of truth until someone regenerates it deliberately with the CLI."""
    _gate(limits.sweep, request)
    return fleet.prescribe(store.all_cases())


@api.post("/api/autopsy")
async def autopsy(request: Request):
    """Stream an autopsy of a trace posted as JSON. Server-sent events."""
    _gate(limits.autopsy, request)
    try:
        raw = await request.json()
    except Exception:
        raise HTTPException(400, "body must be a trace in JSON")
    try:
        t = load(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if os.environ.get("CORONER_REDACT", "1") != "0":
        t = redact(t)
    ev = extract(t)

    q: asyncio.Queue = asyncio.Queue()

    async def emit(e):
        await q.put(e)

    async def work():
        try:
            # Deliberately not stored. Whatever a visitor posts is theirs; it is
            # streamed back to them and forgotten, never added to the graveyard
            # everyone else sees.
            r = await perform_async(t, ev, on_event=emit)
            await q.put({"done": True, "report": r.as_dict()})
        except Exception as e:                     # the client must hear about it
            await q.put({"error": f"{type(e).__name__}: {e}"})
        finally:
            await q.put(None)

    async def stream():
        yield f"data: {json.dumps({'started': True, 'evidence': {'signals': ev.signals, 'prior_cause': ev.prior_cause, 'progress': ev.progress, 'killing_step': ev.killing_step}, 'title': t.title, 'run_id': t.run_id})}\n\n"
        task = asyncio.create_task(work())
        try:
            while (e := await q.get()) is not None:
                yield f"data: {json.dumps(e)}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@api.post("/api/sweep")
async def sweep(request: Request, after: int = watch.SILENT_AFTER, limit: int = 10):
    """Look for runs that have gone quiet and autopsy them without being asked.

    Driven by Cloud Scheduler. Safe to call by hand — it skips anything it has
    already examined."""
    _gate(limits.sweep, request)
    return (await watch.sweep(after=after, limit=min(limit, 10))).as_dict()


@api.get("/api/sweep")
def last_sweep():
    return store.get_meta("sweep") or {"at": None, "watched": 0, "autopsied": []}


@api.post("/api/case/{run_id}/resume")
def hand_back(run_id: str):
    """Hand this run's resume plan to the configured orchestrator."""
    c = store.get(run_id)
    if not c:
        raise HTTPException(404, f"no case file for {run_id}")
    return resume.hand_back(c).as_dict()


@api.get("/api/resume/target")
def resume_target():
    url = os.environ.get(resume.WEBHOOK, "")
    return {"configured": bool(url), "endpoint": url}


@api.get("/api/sample")
def sample():
    """A real trace from the corpus, for the 'try it' button."""
    d = DATA / "sample-trace.json"
    if not d.exists():
        raise HTTPException(404, "no sample trace shipped")
    return json.loads(d.read_text())


@api.get("/")
def index():
    return FileResponse(WEB / "index.html")


api.mount("/", StaticFiles(directory=WEB), name="web")
