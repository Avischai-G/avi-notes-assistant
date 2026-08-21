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

from app import fleet, store, watch
from app.autopsy import STAGES, perform_async
from app.findings import CAUSES, extract
from app.redact import redact
from app.traces import load

WEB = Path(__file__).parent / "web"
DATA = Path(__file__).parent / "data"

api = FastAPI(title="Coroner", description="Post-mortems for dead agent runs.")


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
def fleet_recompute():
    d = fleet.prescribe(store.all_cases())
    (DATA / "fleet.json").write_text(json.dumps(d, indent=2))
    return d


@api.post("/api/autopsy")
async def autopsy(request: Request):
    """Stream an autopsy of a trace posted as JSON. Server-sent events."""
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
            r = await perform_async(t, ev, on_event=emit)
            store.save(r.as_dict())
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
async def sweep(after: int = watch.SILENT_AFTER, limit: int = 10):
    """Look for runs that have gone quiet and autopsy them without being asked.

    Driven by Cloud Scheduler. Safe to call by hand — it skips anything it has
    already examined."""
    return (await watch.sweep(after=after, limit=limit)).as_dict()


@api.get("/api/sweep")
def last_sweep():
    return store.get_meta("sweep") or {"at": None, "watched": 0, "autopsied": []}


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
