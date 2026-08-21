"""Coroner as a service. Runs on Cloud Run.

Endpoints are thin: everything interesting is in app/. The one non-obvious
piece is /api/autopsy, which streams the pipeline as it runs so the caller
watches six agents work instead of a spinner.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import fleet, limits, resume, store, watch
from app.autopsy import STAGES, agent_cards, perform_async, watch_autopsy
from app.findings import CAUSES, extract
from app.redact import redact
from app.traces import load

WEB = Path(__file__).parent / "web"
DATA = Path(__file__).parent / "data"
MAX_REQUEST_BYTES = 1024 * 1024
REQUEST_BODY_TIMEOUT = 10
JUDGE_KEY = "CORONER_JUDGE_KEY"
JUDGE_HEADER = "x-coroner-judge-key"

api = FastAPI(title="Coroner", description="Post-mortems for dead agent runs.")


def _caller(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else
            (request.client.host if request.client else "unknown"))


def _gate(limiter: limits.Limiter, request: Request) -> None:
    """These endpoints spend money. Refuse politely rather than quietly billing."""
    expected = os.environ.get(JUDGE_KEY, "")
    supplied = request.headers.get(JUDGE_HEADER, "")
    if expected and supplied and secrets.compare_digest(supplied, expected):
        return
    ok, wait = limiter.check(_caller(request))
    if not ok:
        raise HTTPException(429, f"Rate limited — this endpoint runs live model calls. "
                                 f"Try again in {wait}s.",
                            headers={"Retry-After": str(wait)})


async def _trace_json(request: Request):
    """Read one bounded JSON body, including when Content-Length is absent."""
    declared = request.headers.get("content-length")
    if declared:
        try:
            declared_size = int(declared)
        except ValueError as exc:
            raise HTTPException(400, "Content-Length must be an integer") from exc
        if declared_size < 0:
            raise HTTPException(400, "Content-Length must not be negative")
        if declared_size > MAX_REQUEST_BYTES:
            raise HTTPException(
                413, f"request body exceeds the {MAX_REQUEST_BYTES}-byte maximum"
            )

    async def read() -> bytes:
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                raise HTTPException(
                    413, f"request body exceeds the {MAX_REQUEST_BYTES}-byte maximum"
                )
            body.extend(chunk)
        return bytes(body)

    try:
        async with asyncio.timeout(REQUEST_BODY_TIMEOUT):
            body = await read()
    except HTTPException:
        raise
    except TimeoutError as exc:
        raise HTTPException(
            408, f"request body was not received within {REQUEST_BODY_TIMEOUT} seconds"
        ) from exc
    except Exception as exc:
        raise HTTPException(400, "could not read request body") from exc

    def reject_constant(value: str):
        raise ValueError(f"non-finite number {value}")

    try:
        return json.loads(body, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            400, f"body must be valid JSON (line {exc.lineno}, column {exc.colno})"
        ) from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "body must be valid UTF-encoded JSON") from exc
    except RecursionError as exc:
        raise HTTPException(400, "JSON nesting is too deep") from exc
    except ValueError as exc:
        raise HTTPException(400, f"body must be valid JSON: {exc}") from exc


async def _posted_trace(request: Request):
    """The trace a caller posted, redacted, with its rule-based evidence."""
    raw = await _trace_json(request)
    try:
        t = load(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if os.environ.get("CORONER_REDACT", "1") != "0":
        t = redact(t)
    return t, extract(t)


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
    return {"ok": True,
            "model": os.environ.get("CORONER_MODEL", "gemini-3.5-flash"),
            "judge_key_configured": bool(os.environ.get(JUDGE_KEY, ""))}


@api.get("/api/taxonomy")
def taxonomy():
    return {k: {"label": v[0], "meaning": v[1], "prevention": v[2]} for k, v in CAUSES.items()}


@api.get("/api/stages")
def stages():
    return [{"agent": a, "label": l, "does": d} for a, l, d in STAGES]


@api.get("/api/agents")
def agents():
    """The six agents in execution order, each with the markdown file that was
    loaded into it. Same object the model was sent — see app/autopsy.py."""
    return agent_cards()


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
    cases = store.all_cases()
    cached = DATA / "fleet.json"
    if cached.exists():
        return fleet.finalize(json.loads(cached.read_text()), cases)
    return fleet.prescribe(cases)


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
    t, ev = await _posted_trace(request)

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


@api.post("/api/autopsy/stream")
async def autopsy_stream(request: Request):
    """The same autopsy as /api/autopsy, reported stage by stage while it runs.

    Named server-sent events: `stage` per agent as it starts and finishes, then
    one `done` carrying the finished case, or `error`. The three investigators
    all report `start` before any reports `done` and share one `group`, because
    a viewer has to be able to see that three things are running at once.

    Deliberately not stored, exactly like /api/autopsy: whatever a visitor
    posts is streamed back to them and forgotten.
    """
    _gate(limits.autopsy, request)
    t, ev = await _posted_trace(request)

    async def stream():
        async for name, data in watch_autopsy(t, ev):
            yield f"event: {name}\ndata: {json.dumps(data)}\n\n"

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


# Three real dead runs, picked for contrast: one died 85% finished, one never
# started, one died mid-step. Keyed by run id — the file is named after the
# chat it came from, which is not the same thing. An allowlist, not a lookup:
# nothing a caller sends reaches the filesystem.
SAMPLES = [
    ("3f8c6a0e-e3c5-4b89-9669-15081c113762", "e5f226c3-77e5-4711-b519-ec2a6037baaa",
     "28 steps done, then it stopped dead"),
    ("02266df1-6d2e-42be-8239-c243bd0896de", "e5feac8f-a837-4780-a127-8887ab68d04d",
     "All six steps waiting on a human"),
    ("ccf2c535-44fa-40cf-8b10-19cbeb5385ba", "752b90f2-2b14-4117-856b-0439cb5d3ec0",
     "Killed mid-step by an orchestrator restart"),
]
TRACE_FILE = {run_id: chat_id for run_id, chat_id, _ in SAMPLES}


@api.get("/api/samples")
def samples():
    return [{"run_id": r, "label": lab} for r, _, lab in SAMPLES]


@api.get("/api/samples/{run_id}")
def sample_trace(run_id: str):
    """The raw trace behind one sample button, ready to POST straight back."""
    chat_id = TRACE_FILE.get(run_id)
    if not chat_id:
        raise HTTPException(404, f"{run_id} is not one of the sample runs")
    p = DATA / "demo-traces" / f"{chat_id}.json"
    if not p.exists():
        raise HTTPException(404, f"no trace shipped for {run_id}")
    return json.loads(p.read_text())


@api.get("/")
def index():
    return FileResponse(WEB / "index.html")


api.mount("/", StaticFiles(directory=WEB), name="web")
