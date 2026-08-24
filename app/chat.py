"""Task organizer chat routes and setup.

One ADK LlmAgent with gemini-3.5-flash at global location.
SSE chat endpoint that distinguishes answer text, tool activity, completion, error.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

try:
    from google.cloud import firestore
except ImportError:
    firestore = None

from app.channel_store import LocalChannelStore, FirestoreChannelStore, Message
from app.automations import (
    AutomationRunner,
    DEFAULT_AUTOMATIONS,
    FirestoreAutomationStore,
    LocalAutomationStore,
)
from app.notion_mcp import NotionConfigurationError
from app.notion_task_store import NotionTaskStore
from app.knowledge import OrganizerKnowledge, build_organizer_knowledge
from app.learning import create_learning_router
from app.task_planning import DayPlanner
from app.task_store import FakeTaskStore
from app.organizer import TaskOrganizerAgent


# Global instances
_channel_store: Optional[object] = None
_task_store: Optional[object] = None
_agent: Optional[TaskOrganizerAgent] = None
_knowledge: Optional[OrganizerKnowledge] = None
_automation_store: Optional[object] = None
_automation_runner: Optional[AutomationRunner] = None
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
    global _channel_store, _task_store, _agent, _knowledge, _automation_store, _automation_runner

    # A failed re-initialization must not leave an earlier fake store reachable.
    _channel_store = None
    _task_store = None
    _agent = None
    _knowledge = None
    _automation_store = None
    _automation_runner = None

    # Channel store
    db = None
    if use_firestore:
        db = _create_firestore_client()
        _channel_store = FirestoreChannelStore(db)
        _automation_store = FirestoreAutomationStore(db)
    else:
        _channel_store = LocalChannelStore()
        _automation_store = LocalAutomationStore()

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
            model=os.environ.get("CORONER_MODEL", "gemini-3.5-flash"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            knowledge=_knowledge,
        )
    except ValueError as e:
        raise RuntimeError(f"Agent initialization failed: {e}")

    for definition in DEFAULT_AUTOMATIONS:
        automation = _automation_store.get(definition.id)
        if automation is None:
            _automation_store.save(deepcopy(definition))
            automation = _automation_store.get(definition.id)
        _channel_store.ensure_channel(automation.channel_id)

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


def register_chat_routes(app: FastAPI) -> None:
    """Register chat and channel routes on the FastAPI app."""

    app.include_router(create_learning_router(get_knowledge))

    @app.get("/api/health")
    def health():
        """Health check with eligibility information.

        Reports the actual agent's model and location, not environment variables.
        If they differ, something is wrong with initialization.
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
    def get_channel(channel_id: str):
        """Get full transcript for a channel."""
        channel_store, task_store, agent = get_stores()
        messages = channel_store.get_channel(channel_id)
        return {
            "channel_id": channel_id,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                }
                for msg in messages
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

        async def stream_response():
            """Stream the agent's response as SSE."""
            try:
                # Stream chunks from the agent
                async for chunk in agent.chat(
                    user_message=user_message,
                    channel_store=channel_store,
                    task_store=task_store,
                    channel_id=channel_id,
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

    @app.get("/api/automations")
    def list_automations():
        """Return the fixed automation channels, never a run-history sidebar."""
        return {
            "automations": [
                {
                    "id": automation.id,
                    "name": automation.name,
                    "enabled": automation.enabled,
                    "schedule": automation.schedule,
                    "channel_id": automation.channel_id,
                }
                for automation in _automation_store.list()
            ]
        }

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
