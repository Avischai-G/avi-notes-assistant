"""A stand-in for the thing on the other end of the loop.

Coroner's job ends when it hands a resume plan to whatever runs your agents.
That is your orchestrator, not mine — so this is a deliberately dumb receiver
that accepts a plan, queues it, and shows the queue. It exists so the loop can
be demonstrated end to end across two services instead of being described.

    uvicorn stub_orchestrator:api --port 8090
"""
from __future__ import annotations

import html
import json
import os
import secrets
import time
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

import app  # noqa: F401  (loads .env)
from app import resume as handoff, store

QUEUE = "resume_queue"
api = FastAPI(title="Stub orchestrator", description="Receives resume plans from Coroner.")

ShortText = Annotated[str, Field(max_length=256)]
LongText = Annotated[str, Field(max_length=16_384)]


class ResumePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    run_id: Annotated[str, Field(min_length=1, max_length=256)]
    title: LongText | None = None
    cause_of_death: ShortText | None = None
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None
    resume_at: ShortText | None = None
    skip: list[ShortText] = Field(default_factory=list, max_length=500)
    proceed_under: LongText | None = None
    restart_prompt: Annotated[str, Field(min_length=1, max_length=16_384)]
    salvage: LongText | None = None


def _db():
    from google.cloud import firestore
    return firestore.Client(project=os.environ["GOOGLE_CLOUD_PROJECT"], database=store.DATABASE)


def _authorize(request: Request) -> None:
    expected = os.environ.get(handoff.SECRET, "")
    supplied = request.headers.get(handoff.AUTH_HEADER, "")
    if not expected or not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "valid resume shared secret required")


def _rows() -> list[dict]:
    rows = [d.to_dict() for d in _db().collection(QUEUE).stream()]
    return sorted(rows, key=lambda r: -(r.get("queued_at") or 0))


def _escape(value) -> str:
    return html.escape(str(value), quote=True)


@api.post("/resume")
async def resume(request: Request):
    _authorize(request)
    try:
        raw = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(400, "body must be valid JSON") from exc
    try:
        plan = ResumePlan.model_validate(raw)
    except ValidationError as exc:
        error = exc.errors(include_url=False, include_input=False)[0]
        field = ".".join(str(part) for part in error["loc"]) or "body"
        raise HTTPException(400, f"invalid resume plan at {field}: {error['msg']}") from exc
    body = plan.model_dump()
    run_id = body["run_id"]
    _db().collection(QUEUE).document(run_id).set({**body, "queued_at": time.time()})
    return {"accepted": True, "queued": run_id,
            "note": "a real orchestrator would now re-dispatch this run"}


@api.get("/queue")
def queue(request: Request):
    _authorize(request)
    return _rows()


@api.get("/", response_class=HTMLResponse)
def index(request: Request):
    _authorize(request)
    rows = _rows()
    items = "".join(
        f"<li><b>{_escape(r.get('title') or r.get('run_id') or '?')}</b>"
        f"<span class=c>{_escape(r.get('cause_of_death', '?'))}</span>"
        f"<p>resume at <code>{_escape(r.get('resume_at') or '—')}</code>, "
        f"skipping {_escape(len(r.get('skip') or []))} banked step(s)</p>"
        f"<pre>{_escape((r.get('restart_prompt') or '')[:600])}</pre></li>"
        for r in rows) or "<li class=empty>Nothing queued yet. Coroner has not handed anything back.</li>"
    return f"""<!doctype html><meta charset=utf-8>
<title>Stub orchestrator — Coroner resume queue</title>
<style>
 body{{background:#0f1113;color:#e8e6e1;font:15px/1.55 -apple-system,system-ui,sans-serif;margin:0;padding:32px}}
 h1{{font-size:20px;margin:0 0 4px}} p.s{{color:#8b9198;margin:0 0 26px;font-size:13px}}
 ul{{list-style:none;padding:0;margin:0;max-width:900px}}
 li{{background:#16191c;border:1px solid #2a2f35;border-left:3px solid #4ec9a5;border-radius:8px;padding:15px 18px;margin-bottom:10px}}
 li.empty{{border-left-color:#5f666d;color:#8b9198}}
 .c{{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#c9a227;margin-left:10px}}
 li p{{color:#8b9198;font-size:13px;margin:6px 0 0}}
 code,pre{{font-family:ui-monospace,Menlo,monospace;font-size:12px}}
 pre{{background:#0b0e10;border:1px solid #2a2f35;border-radius:6px;padding:11px;margin:10px 0 0;white-space:pre-wrap;color:#e8e6e1}}
</style>
<h1>Stub orchestrator</h1>
<p class=s>{_escape(len(rows))} run(s) handed back by Coroner and queued for restart.
This is a stand-in for your orchestrator: it accepts a resume plan at <code>POST /resume</code> and
does nothing clever with it.</p>
<ul>{items}</ul>"""
