"""A stand-in for the thing on the other end of the loop.

Coroner's job ends when it hands a resume plan to whatever runs your agents.
That is your orchestrator, not mine — so this is a deliberately dumb receiver
that accepts a plan, queues it, and shows the queue. It exists so the loop can
be demonstrated end to end across two services instead of being described.

    uvicorn stub_orchestrator:api --port 8090
"""
from __future__ import annotations

import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

import app  # noqa: F401  (loads .env)
from app import store

QUEUE = "resume_queue"
api = FastAPI(title="Stub orchestrator", description="Receives resume plans from Coroner.")


def _db():
    from google.cloud import firestore
    return firestore.Client(project=os.environ["GOOGLE_CLOUD_PROJECT"], database=store.DATABASE)


@api.post("/resume")
async def resume(request: Request):
    plan = await request.json()
    run_id = str(plan.get("run_id") or f"unknown-{time.time()}")
    _db().collection(QUEUE).document(run_id).set({**plan, "queued_at": time.time()})
    return {"accepted": True, "queued": run_id,
            "note": "a real orchestrator would now re-dispatch this run"}


@api.get("/queue")
def queue():
    rows = [d.to_dict() for d in _db().collection(QUEUE).stream()]
    return sorted(rows, key=lambda r: -(r.get("queued_at") or 0))


@api.get("/", response_class=HTMLResponse)
def index():
    rows = queue()
    items = "".join(
        f"<li><b>{(r.get('title') or r.get('run_id') or '?')}</b>"
        f"<span class=c>{r.get('cause_of_death','?')}</span>"
        f"<p>resume at <code>{r.get('resume_at') or '—'}</code>, "
        f"skipping {len(r.get('skip') or [])} banked step(s)</p>"
        f"<pre>{(r.get('restart_prompt') or '')[:600]}</pre></li>"
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
<p class=s>{len(rows)} run(s) handed back by Coroner and queued for restart.
This is a stand-in for your orchestrator: it accepts a resume plan at <code>POST /resume</code> and
does nothing clever with it.</p>
<ul>{items}</ul>"""
