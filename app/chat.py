"""Task organizer chat routes and setup.

One ADK LlmAgent with gemini-3.5-flash at global location.
SSE chat endpoint that distinguishes answer text, tool activity, completion, error.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from copy import deepcopy
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

try:
    from google.cloud import firestore
except ImportError:
    firestore = None

from app.channel_store import LocalChannelStore, FirestoreChannelStore, Message
from app.automations import (
    Automation,
    AutomationRunner,
    DEFAULT_AUTOMATIONS,
    FirestoreAutomationStore,
    LocalAutomationStore,
    next_run_from_schedule,
)
from app.settings_store import FirestoreSettingsStore, LocalSettingsStore
from app.notion_mcp import NotionConfigurationError
from app.notion_task_store import NotionTaskStore
from app.knowledge import OrganizerKnowledge, build_organizer_knowledge
from app.learning import create_learning_router
from app.task_planning import DayPlanner
from app.task_store import FakeTaskStore
from app.organizer import TaskOrganizerAgent
from app.life import LifeAgent


# Global instances
_channel_store: Optional[object] = None
_task_store: Optional[object] = None
_agent: Optional[TaskOrganizerAgent] = None
_live_voice_agent: Optional[LifeAgent] = None
_knowledge: Optional[OrganizerKnowledge] = None
_automation_store: Optional[object] = None
_automation_runner: Optional[AutomationRunner] = None
_settings_store: Optional[object] = None
DEFAULT_FIRESTORE_DATABASE = "coroner"


def _create_firestore_client():
    if firestore is None:
        raise RuntimeError("Firestore support is unavailable in production mode")
    database = os.environ.get(
        "FIRESTORE_DATABASE", DEFAULT_FIRESTORE_DATABASE
    ).strip()
    if not database:
        raise RuntimeError("FIRESTORE_DATABASE must be non-empty")
    return firestore.Client(
        project=os.environ.get("GOOGLE_CLOUD_PROJECT") or None,
        database=database,
    )


def init_chat_stores(
    use_firestore: bool = True,
    *,
    task_store_override: object | None = None,
) -> tuple:
    """Initialize the chat stores and agent.

    Args:
        use_firestore: Use Firestore for production, LocalChannelStore for tests.
        task_store_override: Explicit test-harness store. Production never supplies it.

    Returns:
        Tuple of (channel_store, task_store, agent)
    """
    global _channel_store, _task_store, _agent, _live_voice_agent, _knowledge, _automation_store, _automation_runner, _settings_store

    # A failed re-initialization must not leave an earlier fake store reachable.
    _channel_store = None
    _task_store = None
    _agent = None
    _live_voice_agent = None
    _knowledge = None
    _automation_store = None
    _automation_runner = None
    _settings_store = None

    # Channel store
    db = None
    if use_firestore:
        db = _create_firestore_client()
        _channel_store = FirestoreChannelStore(db)
        _automation_store = FirestoreAutomationStore(db)
        _settings_store = FirestoreSettingsStore(db)
    else:
        _channel_store = LocalChannelStore()
        _automation_store = LocalAutomationStore()
        _settings_store = LocalSettingsStore()

    # The deterministic fake is test/local-only. Production defaults to the
    # scoped Notion adapter and fails closed when its token or database id is absent.
    if task_store_override is not None:
        if isinstance(task_store_override, FakeTaskStore):
            raise NotionConfigurationError(
                "The explicit task-store override must not be FakeTaskStore"
            )
        _task_store = task_store_override
    else:
        task_store_mode = os.environ.get(
            "TASK_STORE_MODE", "notion" if use_firestore else "fake"
        ).strip().lower()
        if task_store_mode == "notion":
            _task_store = NotionTaskStore.from_env()
        elif task_store_mode == "fake":
            if use_firestore or os.environ.get("K_SERVICE"):
                raise NotionConfigurationError(
                    "FakeTaskStore is local/offline only; production requires "
                    "TASK_STORE_MODE=notion and the complete scoped Notion config"
                )
            _task_store = FakeTaskStore()
        else:
            raise NotionConfigurationError(
                "TASK_STORE_MODE must be exactly 'notion' or 'fake'"
            )

    # Markdown bodies live in the local test directory or /knowledge in production.
    # Firestore holds only durable embedding metadata and private learning events.
    _knowledge = build_organizer_knowledge(db=db)

    # Agent
    try:
        _agent = TaskOrganizerAgent(
            model=os.environ.get("CORONER_MODEL", "gemini-3.7-flash"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            knowledge=_knowledge,
        )
    except ValueError as e:
        raise RuntimeError(f"Agent initialization failed: {e}")

    # The live voice session runs on the live-audio model family; its
    # web_research sub-agent stays on the text model.
    _live_voice_agent = LifeAgent(
        model=os.environ.get("CORONER_LIVE_MODEL", "gemini-live-2.5-flash"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        research_model=os.environ.get("CORONER_MODEL", "gemini-3.7-flash"),
    )

    for definition in DEFAULT_AUTOMATIONS:
        automation = _automation_store.get(definition.id)
        if automation is None:
            _automation_store.save(deepcopy(definition))
            automation = _automation_store.get(definition.id)
        _channel_store.ensure_channel(automation.channel_id)

    _agent.prompt_source = _settings_store.get_system_prompt

    planner = DayPlanner(_task_store)
    _automation_runner = AutomationRunner(
        _automation_store,
        _channel_store,
        _task_store,
        _agent,
        knowledge=_knowledge,
        planner=planner,
    )
    _agent.configure_planning(planner, _automation_runner.save_sweep)

    return _channel_store, _task_store, _agent


def get_stores() -> tuple:
    """Get the initialized stores and agent."""
    if not _channel_store or not _agent:
        raise RuntimeError("Chat stores not initialized. Call init_chat_stores() first.")
    return _channel_store, _task_store, _agent


def get_knowledge() -> OrganizerKnowledge:
    if _knowledge is None:
        raise RuntimeError("Knowledge service not initialized. Call init_chat_stores() first.")
    return _knowledge


async def _body(request: Request) -> dict:
    try:
        return await request.json()
    except Exception as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}")


def _automation_payload(automation) -> dict:
    return {
        "id": automation.id,
        "name": automation.name,
        "prompt": automation.prompt,
        "enabled": automation.enabled,
        "schedule": automation.schedule,
        "channel_id": automation.channel_id,
        "built_in": automation.id in {d.id for d in DEFAULT_AUTOMATIONS},
    }


def _free_automation_id(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "automation"
    candidate, suffix = base, 2
    while _automation_store.get(candidate) is not None:
        candidate, suffix = f"{base}-{suffix}", suffix + 1
    return candidate


def register_chat_routes(app: FastAPI) -> None:
    """Register chat and channel routes on the FastAPI app."""

    app.include_router(create_learning_router(get_knowledge))

    @app.get("/api/health")
    def health():
        """Health check with eligibility information.

        Reports the environment-derived model, location, and framework from initialization.
        These come from the agent's get_config() which validates against constraints.
        """
        channel_store, task_store, agent = get_stores()
        agent_config = agent.get_config()
        return {
            "ok": True,
            "model": agent_config["model"],
            "location": agent_config["location"],
            "framework": agent_config["framework"],
            "firestore_mode": "firestore" if isinstance(channel_store, FirestoreChannelStore) else "local",
            "build_revision": os.environ.get("BUILD_REVISION", "local"),
        }

    @app.post("/api/channels/init")
    def init_channel():
        """Create a new channel and return its ID."""
        channel_store, task_store, agent = get_stores()
        channel_id = channel_store.create_channel()
        return {"channel_id": channel_id}

    @app.get("/api/channels/{channel_id}")
    def get_channel(
        channel_id: str,
        limit: Optional[int] = None,
        before: Optional[int] = None,
    ):
        """Get a channel transcript window.

        Without params this is the full transcript. With `limit`, the newest
        `limit` messages (or the `limit` messages before index `before`) are
        returned; `start` is the index of the first returned message, so the
        client passes `before=start` to page further back.
        """
        channel_store, task_store, agent = get_stores()
        messages = channel_store.get_channel(channel_id)
        total = len(messages)
        end = total if before is None else max(0, min(before, total))
        start = 0 if limit is None or limit < 1 else max(0, end - limit)
        return {
            "channel_id": channel_id,
            "total": total,
            "start": start,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                }
                for msg in messages[start:end]
            ],
        }

    @app.post("/api/channels/{channel_id}/chat")
    async def chat(channel_id: str, request: Request):
        """Stream a chat response for the organizer agent.

        POST body: {"message": "user message"}
        Response: SSE stream with chunks like: data: {"text": "..."} or data: {"done": true}
        """
        channel_store, task_store, agent = get_stores()

        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(400, f"Invalid JSON: {e}")

        user_message = body.get("message", "").strip()
        if not user_message:
            raise HTTPException(400, "message field required and non-empty")

        # Image and PDF attachments ride along as inline model input.
        attachments: list[tuple[str, bytes]] = []
        total_bytes = 0
        for item in body.get("attachments") or []:
            if not isinstance(item, dict):
                raise HTTPException(400, "attachments must be objects")
            mime = str(item.get("type", ""))
            if not (mime.startswith("image/") or mime == "application/pdf"):
                raise HTTPException(
                    400, "Only image and PDF attachments are supported"
                )
            try:
                data = base64.b64decode(str(item.get("data", "")), validate=True)
            except Exception:
                raise HTTPException(400, "Attachment data must be base64")
            total_bytes += len(data)
            if total_bytes > 20 * 1024 * 1024:
                raise HTTPException(413, "Attachments exceed the 20 MB limit")
            if data:
                attachments.append((mime, data))

        async def stream_response():
            """Stream the agent's response as SSE."""
            try:
                # Stream chunks from the agent
                async for chunk in agent.chat(
                    user_message=user_message,
                    channel_store=channel_store,
                    task_store=task_store,
                    channel_id=channel_id,
                    attachments=attachments,
                ):
                    yield f"data: {json.dumps(chunk)}\n\n"

            except Exception as e:
                error_chunk = {"error": f"{type(e).__name__}: {e}"}
                yield f"data: {json.dumps(error_chunk)}\n\n"

        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.websocket("/api/live/{channel_id}")
    async def live_session(websocket: WebSocket, channel_id: str):
        """One live voice session: browser audio in, agent audio + transcripts out."""
        await websocket.accept()
        try:
            channel_store, task_store, agent = get_stores()
            if _live_voice_agent is None:
                raise RuntimeError("Live voice agent not initialized")
            await _live_voice_agent.live_bridge(
                websocket, channel_store, task_store, channel_id
            )
        except WebSocketDisconnect:
            pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    @app.get("/api/settings")
    def get_settings():
        return {"system_prompt": _settings_store.get_system_prompt()}

    @app.put("/api/settings")
    async def put_settings(request: Request):
        body = await _body(request)
        prompt = str(body.get("system_prompt") or "").strip()
        if not prompt:
            raise HTTPException(400, "system_prompt required and non-empty")
        _settings_store.set_system_prompt(prompt)
        return {"system_prompt": prompt}

    @app.get("/api/automations")
    def list_automations():
        """Return the automation channels, never a run-history sidebar."""
        return {"automations": [_automation_payload(a) for a in _automation_store.list()]}

    @app.post("/api/automations")
    async def create_automation(request: Request):
        body = await _body(request)
        name = str(body.get("name") or "").strip() or "New automation"
        schedule = str(body.get("schedule") or "daily").strip()
        automation_id = _free_automation_id(name)
        automation = Automation(
            id=automation_id,
            name=name,
            prompt=str(body.get("prompt") or "").strip(),
            schedule=schedule,
            enabled=bool(body.get("enabled", True)),
            channel_id=f"automation-{automation_id}",
            next_run_at=next_run_from_schedule(schedule, time.time()),
        )
        _automation_store.save(automation)
        _channel_store.ensure_channel(automation.channel_id)
        return _automation_payload(automation)

    @app.patch("/api/automations/{automation_id}")
    async def update_automation(automation_id: str, request: Request):
        automation = _automation_store.get(automation_id)
        if automation is None:
            raise HTTPException(404, "automation not found")
        body = await _body(request)
        for field in ("name", "prompt", "schedule"):
            if field in body:
                setattr(automation, field, str(body[field] or "").strip())
        if "enabled" in body:
            automation.enabled = bool(body["enabled"])
        automation.next_run_at = next_run_from_schedule(automation.schedule, time.time())
        _automation_store.save(automation)
        return _automation_payload(automation)

    @app.delete("/api/automations/{automation_id}")
    def delete_automation(automation_id: str):
        # The two built-ins are referenced by id from the planning path.
        if automation_id in {definition.id for definition in DEFAULT_AUTOMATIONS}:
            raise HTTPException(409, "built-in automations cannot be deleted")
        if _automation_store.get(automation_id) is None:
            raise HTTPException(404, "automation not found")
        _automation_store.delete(automation_id)
        return {"deleted": automation_id}

    @app.post("/api/automations/{automation_id}/run")
    async def run_automation(automation_id: str, place: Optional[str] = None):
        try:
            return await _automation_runner.run(
                automation_id, force=True, place=place
            )
        except KeyError:
            raise HTTPException(404, "automation not found")

    @app.post("/api/automations/nightly-plan/pick")
    async def pick_nightly_plan(request: Request):
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(400, f"Invalid JSON: {exc}")
        plan = body.get("plan")
        if plan not in {"A", "B"}:
            raise HTTPException(400, "plan must be A or B")
        try:
            return _automation_runner.pick_plan(plan)
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.post("/api/automations/tick")
    async def automation_tick():
        return {"results": await _automation_runner.tick()}
