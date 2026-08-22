"""Task organizer chat routes and setup.

One ADK LlmAgent with gemini-3.5-flash at global location.
SSE chat endpoint that distinguishes answer text, tool activity, completion, error.
"""
from __future__ import annotations

import json
import os
import asyncio
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

try:
    from firebase_admin import firestore
except ImportError:
    firestore = None

from app.channel_store import LocalChannelStore, FirestoreChannelStore, Message
from app.context_window import ContextWindow
from app.task_store import FakeTaskStore
from app.organizer import TaskOrganizerAgent


# Global instances
_channel_store: Optional[object] = None
_task_store: Optional[object] = None
_agent: Optional[TaskOrganizerAgent] = None


def init_chat_stores(use_firestore: bool = True) -> tuple:
    """Initialize the chat stores and agent.

    Args:
        use_firestore: Use Firestore for production, LocalChannelStore for tests.

    Returns:
        Tuple of (channel_store, task_store, agent)
    """
    global _channel_store, _task_store, _agent

    # Channel store
    if use_firestore and firestore:
        try:
            db = firestore.client()
            _channel_store = FirestoreChannelStore(db)
        except Exception as e:
            print(f"Warning: Firestore init failed, using local store: {e}")
            _channel_store = LocalChannelStore()
    else:
        _channel_store = LocalChannelStore()

    # Task store (fake for now)
    _task_store = FakeTaskStore()

    # Agent
    try:
        _agent = TaskOrganizerAgent(
            model=os.environ.get("CORONER_MODEL", "gemini-3.5-flash"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        )
    except ValueError as e:
        raise RuntimeError(f"Agent initialization failed: {e}")

    return _channel_store, _task_store, _agent


def get_stores() -> tuple:
    """Get the initialized stores and agent."""
    if not _channel_store or not _agent:
        raise RuntimeError("Chat stores not initialized. Call init_chat_stores() first.")
    return _channel_store, _task_store, _agent


def register_chat_routes(app: FastAPI) -> None:
    """Register chat and channel routes on the FastAPI app."""

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

    @app.get("/api/tasks")
    def list_tasks(lane: Optional[str] = None):
        """List tasks, optionally filtered by lane."""
        channel_store, task_store, agent = get_stores()
        tasks = task_store.list_tasks(lane)
        return {
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "lane": t.lane,
                }
                for t in tasks
            ],
        }
