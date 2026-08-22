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

from app import fleet, limits, resume, store, watch, chat
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

api = FastAPI(title="Task Organizer", description="A task-organizing chat app.")

# Initialize chat infrastructure on startup
try:
    use_firestore = os.environ.get("USE_FIRESTORE", "1") != "0"
    chat.init_chat_stores(use_firestore=use_firestore)
except Exception as e:
    print(f"Warning: Chat initialization failed: {e}")


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


# OLD CORONER ENDPOINTS — REPLACED BY TASK CHAT
# The following autopsy, fleet, and case routes served the old Coroner website.
# They are no longer registered. Use /api/channels/* for the new task-chat interface.
#
# All old imports (autopsy, fleet, limits, resume, watch, store, etc.) are kept
# for backward compatibility if Cloud Scheduler or other integrations call them,
# but these routes are not exposed to new clients.


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


# Register chat routes
chat.register_chat_routes(api)

@api.get("/")
def index():
    # Serve the new task-chat HTML from web/index.html
    index_file = WEB / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    # Fallback
    return {"message": "Task Chat - use /api/channels/init to start"}


# Mount remaining static files (if any)
try:
    api.mount("/", StaticFiles(directory=WEB), name="web")
except Exception:
    pass  # OK if no static files directory
