"""Authenticated local app used only for the approved one-time live story."""
from __future__ import annotations

import atexit
import hashlib
import hmac
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import chat
from app.notion_task_store import NotionTaskStore
from scripts.demo_reset import load_notion_environment
from tools.marker_scoped_task_store import MarkerScopedTaskStore


WEB = Path(__file__).resolve().parents[1] / "web"
MARKER = os.environ.get("LIVE_ACCEPTANCE_MARKER", "")
if not MARKER:
    raise RuntimeError("LIVE_ACCEPTANCE_MARKER is required")

load_notion_environment()
scoped_store = MarkerScopedTaskStore(NotionTaskStore.from_env(), MARKER)
atexit.register(scoped_store.close)
chat.init_chat_stores(use_firestore=True, task_store_override=scoped_store)

api = FastAPI(title="Avi's Notes Assistant — approved live acceptance")
chat.register_chat_routes(api)


def _authorize(request: Request) -> None:
    supplied = request.headers.get("X-Live-Acceptance-Marker", "")
    if not hmac.compare_digest(supplied, MARKER):
        raise HTTPException(404, "not found")


@api.get("/__acceptance__/rows", include_in_schema=False)
def acceptance_rows(request: Request):
    """Return synthetic marker rows only; unmarked rows never cross this seam."""
    _authorize(request)
    return {
        "rows": [
            {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "when": task.when,
                "place": task.place,
                "minutes": task.minutes,
                "notes": task.notes,
            }
            for task in scoped_store.list_tasks()
        ]
    }


@api.post("/__acceptance__/seed-dream", include_in_schema=False)
def acceptance_seed_dream(request: Request):
    """Seed exactly one synthetic pending observation in the dedicated live root."""
    _authorize(request)
    knowledge = chat.get_knowledge()
    target = MARKER.casefold()
    if target in knowledge.pending_dream_targets():
        return {"status": "already-seeded", "target": target}
    logical_path = knowledge.dream_skill(
        target,
        f"Synthetic observation for release trace {MARKER}.",
        f"Seeded synthetic acceptance observation {MARKER}",
    )
    return {"status": "seeded", "target": target, "path": logical_path}


@api.get("/__acceptance__/knowledge-manifest", include_in_schema=False)
def acceptance_knowledge_manifest(request: Request):
    """Expose hashes and counts for the synthetic target, never Markdown bodies."""
    _authorize(request)
    knowledge = chat.get_knowledge()
    target = MARKER.casefold()
    skill = knowledge.store.skill_path(target)
    dreams = knowledge.store.list_dream_paths(target)
    return {
        "target": target,
        "skill_exists": skill.is_file(),
        "skill_sha256": (
            hashlib.sha256(skill.read_bytes()).hexdigest() if skill.is_file() else None
        ),
        "dream_note_count": len(dreams),
        "pending": target in knowledge.pending_dream_targets(),
    }


@api.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB / "index.html")


api.mount("/", StaticFiles(directory=WEB), name="web")
