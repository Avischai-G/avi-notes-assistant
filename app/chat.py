"""Task organizer chat routes and setup.

One ADK LlmAgent with gemini-3.5-flash at global location.
SSE chat endpoint that distinguishes answer text, tool activity, completion, error.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import time
import uuid
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse

try:
    from google.cloud import firestore
except ImportError:
    firestore = None

from app.channel_store import LocalChannelStore, FirestoreChannelStore
from app.automations import (
    Automation,
    AutomationRunner,
    DEFAULT_AUTOMATIONS,
    FirestoreAutomationStore,
    LocalAutomationStore,
    RETIRED_AUTOMATION_IDS,
    reconcile_triggers,
)
from app.settings_store import FirestoreSettingsStore, LocalSettingsStore
from app.notion_mcp import NotionConfig, NotionConfigurationError
from app.notion_task_store import NotionTaskStore
from app.knowledge import OrganizerKnowledge, build_organizer_knowledge, knowledge_root
from app.task_planning import BoardReview, FREQUENCIES
from app.task_store import FakeTaskStore
from app.organizer import MEMORY_WORD_CAP, TaskOrganizerAgent, _eligible_model
from app.life import LIFE_PROMPT, LifeAgent


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
            config = NotionConfig.from_env()
            stored_id = str(
                _settings_store.get_value("notion_database_id") or ""
            ).strip()
            if stored_id:
                config = replace(config, tasks_database_id=stored_id)
            _task_store = NotionTaskStore(config)
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

    # An evaluator's stored Gemini API key replaces Vertex for model calls.
    # Keys are device-local now; scrub any key an older build left in Firestore.
    if _settings_store.get_value("gemini_api_key"):
        _settings_store.set_value("gemini_api_key", None)
    _keyed_agents.clear()
    _build_agents()

    for retired in RETIRED_AUTOMATION_IDS:
        # Dropped automations would otherwise sit in Firestore forever.
        if _automation_store.get(retired) is not None:
            _automation_store.delete(retired)

    for definition in DEFAULT_AUTOMATIONS:
        if _automation_store.get(definition.id) is None:
            _automation_store.save(deepcopy(definition))

    reconcile_triggers(_automation_store, time.time())
    for automation in _automation_store.list():
        _channel_store.ensure_channel(automation.channel_id)

    return _channel_store, _task_store, _agent


# The Gemini Live prebuilt voices the Settings picker offers.
LIVE_VOICES = ("Puck", "Charon", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr")

# The server's own key (Secret Manager → env). Never sent to any client.
_SERVER_API_KEY = os.environ.get("GEMINI_DEFAULT_API_KEY", "").strip()

# When "1", browser requests must carry a device-local key: the server's own
# credentials never fund a stranger's chat, voice session, or manual
# automation run. Scheduled automations still run on server credentials.
_REQUIRE_DEVICE_KEY = os.environ.get("CORONER_REQUIRE_DEVICE_KEY", "").strip() == "1"
_KEY_REQUIRED_DETAIL = (
    "This app runs on your own Gemini API key. Add one in Settings first."
)

# A visitor's device-local key never touches env or disk: it selects a cached
# per-key agent pair instead. Bounded so junk keys can't grow it forever.
_keyed_agents: dict[str, tuple] = {}
_KEYED_AGENTS_MAX = 8
_API_KEY_PATTERN = re.compile(r"[A-Za-z0-9_\-]{20,200}")
# A model id is free text from Settings, so it is shape-checked like the key.
_MODEL_PATTERN = re.compile(r"[A-Za-z0-9._\-/]{1,120}")


def _current_database_id() -> str:
    """The Notion database the app is pointed at right now, or empty."""
    config = getattr(_task_store, "config", None)
    return getattr(config, "tasks_database_id", "") or ""


_ATTACHMENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/heic": "heic",
    "application/pdf": "pdf",
}
_ATTACHMENT_NAME = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{1,4}$")
# The public origin of the current request, for links a Notion page can fetch.
_request_origin: ContextVar[str] = ContextVar("request_origin", default="")


def _attachments_dir() -> Path:
    directory = knowledge_root() / "attachments"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _publish_attachment(mime: str, data: bytes) -> str:
    """Write one attached file to disk and return its public URL."""
    name = f"{uuid.uuid4().hex}.{_ATTACHMENT_TYPES.get(mime, 'bin')}"
    (_attachments_dir() / name).write_bytes(data)
    return f"{_request_origin.get()}/files/{name}"


def _live_instruction() -> str:
    """The live prompt plus the user's own languages, when they named them."""
    prompt = str(_settings_store.get_value("live_prompt") or "") or LIFE_PROMPT
    languages = str(_settings_store.get_value("live_languages") or "").strip()
    if languages:
        prompt += (
            f"\n\nThe user speaks only these languages: {languages}. Answer in "
            "whichever of them they are speaking; never use any other language."
        )
    return prompt


def _memory() -> str:
    """What the organizer has been asked to remember about the user."""
    return str(_settings_store.get_value("memory") or "").strip()


def _with_memory(prompt: str) -> str:
    """The prompt plus the stored memory, only when there is one."""
    memory = _memory()
    if not memory:
        return prompt
    return f"{prompt}\n\nStored memory about the user:\n{memory}"


def _settings_payload() -> dict:
    """Everything Settings shows. API keys are device-local, never served."""
    return {
        "system_prompt": _settings_store.get_system_prompt(),
        "live_prompt": str(_settings_store.get_value("live_prompt") or "") or LIFE_PROMPT,
        "voice_name": str(_settings_store.get_value("voice_name") or ""),
        "language_code": str(_settings_store.get_value("language_code") or ""),
        "voices": list(LIVE_VOICES),
        "require_key": _REQUIRE_DEVICE_KEY,
        "default_model": _default_model(),
        "memory": _memory(),
        "live_languages": str(_settings_store.get_value("live_languages") or ""),
        "notion_database_id": _current_database_id(),
    }


def _app_map() -> str:
    """The navigator's operating rules and app map, rebuilt per session and
    appended to whatever instructions are stored — a customized prompt still
    gets current tool behavior."""
    lines = [
        "Operating rules (always in force):",
        "- Decide and act immediately. Never ask permission, and never ask a "
        "clarifying question when any sensible reading exists — pick it and act.",
        "- Your own tools only read the board: list_tasks, search_tasks, "
        "read_task_details, read_task_comments answer questions directly.",
        "- Everything else — creating, changing, completing or deleting tasks, "
        "remembering things, anything beyond the board — you do by calling "
        "send_task_to_chat with the user's intent as one plain sentence. "
        "Never say you sent something without having called it; the call IS "
        "the sending, and the instruction appears in the chat instantly.",
        "- The task assistant in the chat is terse and reliable: it answers "
        "in one line, writes tasks without inventing fields, and handles "
        "renames, deletes, comments, checklists, file attachments, memory "
        "and automations. Trust it; do not over-specify or split into steps.",
        "- When send_task_to_chat returns answer_pending, call "
        "wait_for_chat_answer once and speak the result.",
        "- navigate moves the app; run_automation starts one now.",
        "",
        "App map:",
        '- Chat channel — navigate target "chat". Instructions you hand off '
        "land here and the task assistant executes them.",
    ]
    for automation in _automation_store.list():
        lines.append(
            f'- Automation "{automation.name}" — id "{automation.id}". '
            "navigate to open its channel; run_automation to start it."
        )
    lines.append(
        '- Settings dialog — navigate target "settings" '
        "(voice, accent, API key, these instructions)."
    )
    return "\n".join(lines)


# The voice agent's rolling memory: the last 8 spoken exchanges per channel,
# stored in the settings doc so follow-ups survive new sessions and restarts.
_VOICE_MEMORY_MAX = 16  # 8 user/assistant pairs


def _voice_memory_key(channel_id: str) -> str:
    return f"voice_memory:{channel_id}"


def _voice_memory_read(channel_id: str) -> list:
    entries = _settings_store.get_value(_voice_memory_key(channel_id))
    return entries if isinstance(entries, list) else []


def _voice_memory_append(channel_id: str, entries: list) -> None:
    kept = (_voice_memory_read(channel_id) + list(entries))[-_VOICE_MEMORY_MAX:]
    _settings_store.set_value(_voice_memory_key(channel_id), kept)


async def _start_automation_by_name(name: str) -> dict:
    """Resolve by name or id and start it without blocking the voice."""
    needle = name.strip().casefold()
    match = next(
        (
            automation
            for automation in _automation_store.list()
            if automation.id.casefold() == needle
            or automation.name.casefold() == needle
        ),
        None,
    )
    if match is None:
        return {
            "started": False,
            "reason": f"No automation called {name!r}",
            "available": [a.name for a in _automation_store.list()],
        }

    async def run() -> None:
        try:
            await _automation_runner.run(match.id, force=True)
        except Exception:
            pass

    task = asyncio.ensure_future(run())
    _background_runs.add(task)
    task.add_done_callback(_background_runs.discard)
    return {
        "started": True,
        "automation": match.name,
        "note": "Running now; its channel will update when it finishes.",
    }


_background_runs: set = set()


def _speech_settings() -> dict:
    return {
        "voice_name": _settings_store.get_value("voice_name"),
        "language_code": _settings_store.get_value("language_code"),
    }


def _live_model_id() -> str:
    """The latest live-audio model. Voice always runs on Vertex: no 3.x model
    supports the live api anywhere yet (1007), and the Gemini API's live
    previews connect but never answer — probed with real speech on both."""
    return os.environ.get("CORONER_LIVE_MODEL", "gemini-live-2.5-flash")


def _default_model() -> str:
    return os.environ.get("CORONER_MODEL", "gemini-3.7-flash")


def _make_agents(api_key: str | None, model: str | None = None) -> tuple:
    """One organizer + one live agent bound to the given key (None = server
    credentials: the server's own key, else Vertex)."""
    try:
        organizer = TaskOrganizerAgent(
            model=model or _default_model(),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            knowledge=_knowledge,
            api_key=api_key,
        )
    except ValueError as e:
        raise RuntimeError(f"Agent initialization failed: {e}")

    # The voice session itself always runs on Vertex (see _live_model_id);
    # a device key still funds the text organizer its tasks are handed to.
    live = LifeAgent(
        model=_live_model_id(),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        speech_settings=_speech_settings,
    )
    organizer.prompt_source = lambda: _with_memory(
        _settings_store.get_system_prompt()
    )
    organizer.memory_source = _memory
    organizer.memory_sink = lambda text: _settings_store.set_value(
        "memory", text.strip() or None
    )
    organizer.file_publisher = _publish_attachment
    live.prompt_source = _live_instruction
    return organizer, live


def _build_agents() -> None:
    """(Re)construct the default agents and the automation runner they share."""
    global _agent, _live_voice_agent, _automation_runner

    _agent, _live_voice_agent = _make_agents(_SERVER_API_KEY or None)
    _automation_runner = AutomationRunner(
        _automation_store,
        _channel_store,
        _task_store,
        _agent,
        review=BoardReview(_task_store),
    )
    # The user can ask the chat to run an automation by name.
    _agent.configure_automations(_automation_runner)


def _agents_for_request_key(api_key: str, model: str | None = None) -> tuple:
    """The agent pair for one device-local (key, model), built on first use."""
    digest = hashlib.sha256(f"{model or ''}:{api_key}".encode()).hexdigest()
    if digest not in _keyed_agents:
        if len(_keyed_agents) >= _KEYED_AGENTS_MAX:
            _keyed_agents.pop(next(iter(_keyed_agents)))
        try:
            organizer, live = _make_agents(api_key, model)
        except RuntimeError as exc:
            # The organizer's own model guard, surfaced as the client's fault.
            raise HTTPException(400, str(exc))
        organizer.configure_automations(_automation_runner)
        _keyed_agents[digest] = (organizer, live)
    return _keyed_agents[digest]


def _request_api_key(raw: str | None) -> str | None:
    """Validate an inbound device key; None when absent, 400 when malformed."""
    key = (raw or "").strip()
    if not key:
        return None
    if not _API_KEY_PATTERN.fullmatch(key):
        raise HTTPException(400, "That does not look like a Gemini API key")
    return key


def _request_model(raw: str | None) -> str | None:
    """Validate an inbound model id; None when absent, 400 when malformed."""
    model = (raw or "").strip()
    if not model:
        return None
    if not _MODEL_PATTERN.fullmatch(model):
        raise HTTPException(400, "That does not look like a model identifier")
    return model


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
        "frequency": automation.frequency,
        "hour": automation.hour,
        "minute": automation.minute,
        "weekday": automation.weekday,
        "channel_id": automation.channel_id,
        "built_in": automation.id in {d.id for d in DEFAULT_AUTOMATIONS},
    }


def _apply_trigger(automation, body: dict) -> None:
    """Take the trigger from the request, then derive its text and next run."""
    frequency = str(body.get("frequency", automation.frequency)).strip().casefold()
    if frequency not in FREQUENCIES:
        raise HTTPException(400, f"frequency must be one of {', '.join(FREQUENCIES)}")
    automation.frequency = frequency
    for name, ceiling in (("hour", 24), ("minute", 60), ("weekday", 7)):
        if name not in body:
            continue
        try:
            value = int(body[name])
        except (TypeError, ValueError):
            raise HTTPException(400, f"{name} must be a whole number")
        if not 0 <= value < ceiling:
            raise HTTPException(400, f"{name} must be between 0 and {ceiling - 1}")
        setattr(automation, name, value)
    automation.schedule = automation.described()
    automation.next_run_at = automation.next_run(time.time())


def _free_automation_id(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "automation"
    candidate, suffix = base, 2
    while _automation_store.get(candidate) is not None:
        candidate, suffix = f"{base}-{suffix}", suffix + 1
    return candidate


def register_chat_routes(app: FastAPI) -> None:
    """Register chat and channel routes on the FastAPI app."""

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

    @app.delete("/api/channels/{channel_id}")
    async def clear_channel(channel_id: str, request: Request):
        """Delete a chat's history: the channel stays, emptied, and the
        voice agent's rolling memory of it goes with it."""
        if _REQUIRE_DEVICE_KEY and not _request_api_key(
            request.headers.get("x-gemini-key")
        ):
            raise HTTPException(401, _KEY_REQUIRED_DETAIL)
        channel_store, _, _ = get_stores()
        channel_store.create_channel(channel_id)
        _settings_store.set_value(_voice_memory_key(channel_id), [])
        return {"cleared": channel_id}

    @app.post("/api/channels/{channel_id}/chat")
    async def chat(channel_id: str, request: Request):
        """Stream a chat response for the organizer agent.

        POST body: {"message": "user message"}
        Response: SSE stream with chunks like: data: {"text": "..."} or data: {"done": true}
        A device-local Gemini key may ride in the X-Gemini-Key header; it
        selects a per-key agent and is never stored or logged.
        """
        channel_store, task_store, agent = get_stores()
        host = request.headers.get("host", "")
        scheme = "http" if host.split(":")[0] in ("127.0.0.1", "localhost") else "https"
        _request_origin.set(f"{scheme}://{host}" if host else "")
        device_key = _request_api_key(request.headers.get("x-gemini-key"))
        device_model = _request_model(request.headers.get("x-gemini-model"))
        if device_key:
            agent, _ = _agents_for_request_key(device_key, device_model)
        elif _REQUIRE_DEVICE_KEY:
            raise HTTPException(401, _KEY_REQUIRED_DETAIL)

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
        """One live voice session: browser audio in, agent audio out.

        The first client frame must be {"type": "init"}; it may carry the
        device-local Gemini key (headers are unavailable to browser
        WebSockets, and a query parameter would land in request logs).
        """
        await websocket.accept()
        try:
            channel_store, task_store, agent = get_stores()
            if _live_voice_agent is None:
                raise RuntimeError("Live voice agent not initialized")
            first = await websocket.receive_json()
            live_agent = _live_voice_agent
            device_key = device_model = None
            if isinstance(first, dict) and first.get("type") == "init":
                device_key = _request_api_key(first.get("api_key"))
                device_model = _request_model(first.get("model"))
            if device_key:
                agent, live_agent = _agents_for_request_key(device_key, device_model)
            elif _REQUIRE_DEVICE_KEY:
                raise HTTPException(401, _KEY_REQUIRED_DETAIL)
            await live_agent.live_bridge(
                websocket,
                channel_store,
                task_store,
                channel_id,
                organizer=agent,
                app_map=_app_map(),
                automation_starter=_start_automation_by_name,
                recall=lambda: _voice_memory_read(channel_id),
                remember=lambda entries: _voice_memory_append(channel_id, entries),
            )
        except WebSocketDisconnect:
            pass
        except HTTPException as exc:
            try:
                await websocket.send_json({"type": "error", "message": exc.detail})
            except Exception:
                pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    @app.get("/files/{name}")
    def serve_attachment(name: str):
        """Serve one stored attachment; names are unguessable hex handles."""
        if not _ATTACHMENT_NAME.fullmatch(name):
            raise HTTPException(404, "No such file")
        path = _attachments_dir() / name
        if not path.is_file():
            raise HTTPException(404, "No such file")
        extension = name.rsplit(".", 1)[1]
        mime = next(
            (m for m, e in _ATTACHMENT_TYPES.items() if e == extension),
            "application/octet-stream",
        )
        return FileResponse(path, media_type=mime)

    @app.post("/api/key-check")
    async def key_check(request: Request):
        """One tiny Gemini API call with the supplied key and model: works or
        why not.

        Key and model ride the X-Gemini-Key / X-Gemini-Model headers like
        every chat request; neither is stored or logged.
        """
        key = _request_api_key(request.headers.get("x-gemini-key"))
        if not key:
            raise HTTPException(400, "Send the key to check in the X-Gemini-Key header")
        model = _request_model(request.headers.get("x-gemini-model")) or _default_model()
        if not _eligible_model(model):
            return {
                "ok": False,
                "reason": f"{model!r} will be refused by the app: it requires "
                "Gemini 3.5 or newer (e.g. gemini-3.7-flash).",
            }
        from google import genai

        try:
            # vertexai=False: GOOGLE_GENAI_USE_VERTEXAI=true is set in the
            # server env and would otherwise route this to Vertex, ignoring
            # the key entirely.
            client = genai.Client(api_key=key, vertexai=False)
            reply = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model,
                    contents="Reply with the single word OK.",
                ),
                timeout=20,
            )
            return {"ok": bool((reply.text or "").strip()), "model": model}
        except asyncio.TimeoutError:
            return {"ok": False, "reason": "The Gemini API did not answer within 20 seconds"}
        except Exception as exc:
            # The genai ClientError stringifies the whole error payload;
            # the human-readable part is its 'message' field.
            match = re.search(r"'message': '([^']+)'", str(exc))
            return {"ok": False, "reason": match.group(1) if match else str(exc)[:200]}

    @app.get("/api/settings")
    def get_settings():
        return _settings_payload()

    @app.put("/api/settings")
    async def put_settings(request: Request):
        body = await _body(request)

        if "system_prompt" in body:
            prompt = str(body.get("system_prompt") or "").strip()
            if not prompt:
                raise HTTPException(400, "system_prompt required and non-empty")
            _settings_store.set_system_prompt(prompt)

        if "live_prompt" in body:
            live_prompt = str(body.get("live_prompt") or "").strip()
            # Storing the untouched default (or nothing) keeps the override empty.
            _settings_store.set_value(
                "live_prompt", "" if live_prompt == LIFE_PROMPT.strip() else live_prompt
            )

        if "memory" in body:
            memory = str(body.get("memory") or "").strip()
            words = len(memory.split())
            if words > MEMORY_WORD_CAP:
                raise HTTPException(
                    400,
                    f"The memory is {words} words; the cap is {MEMORY_WORD_CAP}.",
                )
            _settings_store.set_value("memory", memory or None)

        if "notion_database_id" in body:
            global _task_store
            wanted = str(body.get("notion_database_id") or "").strip().replace("-", "")
            if wanted and wanted != _current_database_id():
                if not re.fullmatch(r"[0-9a-fA-F]{32}", wanted):
                    raise HTTPException(
                        400,
                        "The database ID is the 32-character code in the "
                        "board's URL, before any '?'",
                    )
                if not isinstance(_task_store, NotionTaskStore):
                    raise HTTPException(
                        400,
                        "This offline run uses a local fake board; switching "
                        "boards works on the deployed app",
                    )
                candidate = NotionTaskStore(
                    replace(_task_store.config, tasks_database_id=wanted)
                )
                try:
                    candidate.list_tasks()
                except Exception as exc:
                    raise HTTPException(
                        400,
                        "Could not read that board "
                        f"({type(exc).__name__}). Share it with the app's "
                        "Notion integration first, then try again.",
                    )
                _task_store = candidate
                _settings_store.set_value("notion_database_id", wanted)
                _build_agents()

        if "live_languages" in body:
            languages = str(body.get("live_languages") or "").strip()
            if len(languages) > 120:
                raise HTTPException(400, "live_languages must be 120 characters or fewer")
            _settings_store.set_value("live_languages", languages)

        if "voice_name" in body:
            voice = str(body.get("voice_name") or "").strip()
            if voice and voice not in LIVE_VOICES:
                raise HTTPException(400, f"voice_name must be one of {LIVE_VOICES}")
            _settings_store.set_value("voice_name", voice)

        if "language_code" in body:
            language = str(body.get("language_code") or "").strip()
            if language and not re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}", language):
                raise HTTPException(400, "language_code must look like en-US")
            _settings_store.set_value("language_code", language)

        # gemini_api_key is deliberately not accepted here: device keys live in
        # the browser's local storage and ride per-request headers only.

        return _settings_payload()

    @app.get("/api/automations")
    def list_automations():
        """Return the automation channels, never a run-history sidebar."""
        return {"automations": [_automation_payload(a) for a in _automation_store.list()]}

    @app.post("/api/automations")
    async def create_automation(request: Request):
        body = await _body(request)
        name = str(body.get("name") or "").strip() or "New automation"
        automation_id = _free_automation_id(name)
        automation = Automation(
            id=automation_id,
            name=name,
            prompt=str(body.get("prompt") or "").strip(),
            schedule="",
            enabled=bool(body.get("enabled", True)),
            channel_id=f"automation-{automation_id}",
        )
        _apply_trigger(automation, body)
        _automation_store.save(automation)
        _channel_store.ensure_channel(automation.channel_id)
        return _automation_payload(automation)

    @app.patch("/api/automations/{automation_id}")
    async def update_automation(automation_id: str, request: Request):
        automation = _automation_store.get(automation_id)
        if automation is None:
            raise HTTPException(404, "automation not found")
        body = await _body(request)
        for field in ("name", "prompt"):
            if field in body:
                setattr(automation, field, str(body[field] or "").strip())
        if "enabled" in body:
            automation.enabled = bool(body["enabled"])
        _apply_trigger(automation, body)
        _automation_store.save(automation)
        return _automation_payload(automation)

    @app.delete("/api/automations/{automation_id}")
    def delete_automation(automation_id: str):
        # The built-in is referenced by id from the planning path.
        if automation_id in {definition.id for definition in DEFAULT_AUTOMATIONS}:
            raise HTTPException(409, "built-in automations cannot be deleted")
        if _automation_store.get(automation_id) is None:
            raise HTTPException(404, "automation not found")
        _automation_store.delete(automation_id)
        return {"deleted": automation_id}

    @app.post("/api/automations/{automation_id}/run")
    async def run_automation(
        automation_id: str, request: Request, place: Optional[str] = None
    ):
        # ponytail: the key only gates entry here — the run itself still uses
        # server credentials; rewire the runner per-key if that ever matters.
        if _REQUIRE_DEVICE_KEY and not _request_api_key(
            request.headers.get("x-gemini-key")
        ):
            raise HTTPException(401, _KEY_REQUIRED_DETAIL)
        try:
            return await _automation_runner.run(
                automation_id, force=True, place=place
            )
        except KeyError:
            raise HTTPException(404, "automation not found")

    @app.post("/api/automations/tick")
    async def automation_tick():
        return {"results": await _automation_runner.tick()}
