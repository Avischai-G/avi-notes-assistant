"""The live voice navigator: one fast ADK ``LlmAgent`` beside the organizer.

It drives the app and nothing else — hand a prompt to the chat (the task
assistant executes it), navigate to a pane, or start an automation. It never
touches the board itself; every session's instruction is the Settings live
prompt plus a freshly built app map.
"""
from __future__ import annotations

import asyncio
import base64
import os
import time
from contextvars import ContextVar
from typing import AsyncGenerator, Callable
import uuid

from google.adk.agents import LlmAgent
from google.adk.events import Event
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.channel_store import ChannelStore, Message
from app.context_window import ContextWindow
from app.organizer import (
    DEFAULT_MODEL,
    USER_ID,
    _eligible_model,
    _model_backend,
    _task_dict,
)
from app.task_store import TaskStore


LIFE_PROMPT = """You are the app's live voice navigator. The user speaks; you decide and act at once.

You know the app: a Chat channel where a capable task assistant manages their Notion board, automation channels, and a Settings dialog. The current app map is appended below, after any recent voice conversation — use that conversation to understand what they refer to.

Operating rules:
- Decide and act immediately. Never ask permission, and never ask a clarifying question when any sensible reading exists — pick it and act.
- Your own tools read the board and the web: list_tasks, search_tasks, read_task_details, read_task_comments answer board questions directly, and web_search answers any question about the world — fuel prices, weather, news, anything not connected to the board. Never say you cannot look something up.
- Everything else — creating, changing, completing or deleting tasks, remembering things, anything beyond the board — you do by calling send_task_to_chat with the user's intent as one plain sentence. Never say you sent something without having called it; the call IS the sending, and the instruction appears in the chat instantly.
- The task assistant in the chat is terse and reliable: it answers in one line, writes tasks without inventing fields, and handles renames, deletes, comments, checklists, file attachments, reminders, memory, web answers and automations. Trust it; do not over-specify or split into steps.
- When send_task_to_chat returns answer_pending, carry on; the reply arrives as a line starting with [the task assistant replied] — speak its substance to the user the moment it does. wait_for_chat_answer also fetches it if you prefer to wait.
- navigate moves the app; run_automation starts one now.

Speak in short, quick confirmations — a few words. No markdown, no lists. Answer in the language the user speaks, unless they ask for another."""

APP_NAME = "life"


def _shielded(tool):
    """Any tool failure becomes a result the model can read and recover from."""
    from functools import wraps
    from inspect import iscoroutinefunction

    def failure(exc: Exception) -> dict:
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "hint": "Fix the arguments and retry, or tell the user in one plain sentence.",
        }

    if iscoroutinefunction(tool):
        @wraps(tool)
        async def shielded_async(*args, **kwargs):
            try:
                return await tool(*args, **kwargs)
            except Exception as exc:
                return failure(exc)

        return shielded_async

    @wraps(tool)
    def shielded(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        except Exception as exc:
            return failure(exc)

    return shielded

# How long send_task_to_chat waits before answering "pending", and how long
# wait_for_chat_answer stays with the organizer after that.
QUICK_WAIT_SECONDS = 5
LONG_WAIT_SECONDS = 30


def _install_live_probes() -> None:
    """LIVE_DEBUG=1 only: print compact per-message shapes at the genai and
    ADK layers so Cloud Run logs show exactly where audio stops."""
    from google.genai import live as genai_live
    from google.adk.models import gemini_llm_connection as adk_conn

    if getattr(genai_live.AsyncSession, "_live_probe", False):
        return
    genai_live.AsyncSession._live_probe = True

    wire_receive = genai_live.AsyncSession.receive

    async def wire_wrapped(self, *args, **kwargs):
        async for message in wire_receive(self, *args, **kwargs):
            sc = message.server_content
            print(
                "LIVE_WIRE",
                {
                    "inline": bool(
                        sc and sc.model_turn and any(p.inline_data for p in sc.model_turn.parts or [])
                    ),
                    "text": bool(
                        sc and sc.model_turn and any(p.text for p in sc.model_turn.parts or [])
                    ),
                    "in_t": bool(sc and sc.input_transcription),
                    "out_t": bool(sc and sc.output_transcription),
                    "tc": bool(sc and sc.turn_complete),
                    "gc": bool(sc and sc.generation_complete),
                    "tool": bool(message.tool_call),
                },
                flush=True,
            )
            yield message

    genai_live.AsyncSession.receive = wire_wrapped

    adk_receive = adk_conn.GeminiLlmConnection.receive

    async def adk_wrapped(self, *args, **kwargs):
        async for response in adk_receive(self, *args, **kwargs):
            content = response.content
            print(
                "LIVE_RSP",
                {
                    "inline": bool(
                        content and content.parts and any(p.inline_data for p in content.parts)
                    ),
                    "text": bool(
                        content and content.parts and any(p.text for p in content.parts)
                    ),
                    "partial": response.partial,
                    "in_t": bool(response.input_transcription),
                    "out_t": bool(response.output_transcription),
                    "tc": response.turn_complete,
                },
                flush=True,
            )
            yield response

    adk_conn.GeminiLlmConnection.receive = adk_wrapped


class LifeAgent:
    """The voice navigator: one fast ADK ``LlmAgent`` with three app tools."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        location: str = "global",
        *,
        llm: BaseLlm | None = None,
        speech_settings: Callable[[], dict] | None = None,
        api_key: str | None = None,
    ) -> None:
        if location != "global":
            raise ValueError(f"Location must be 'global', got {location}")
        # Live-audio models (gemini-live-*) carry their own naming scheme and
        # are accepted alongside the gemini-3.5+ text family.
        is_live_model = model.startswith("gemini-") and "live" in model
        if not (_eligible_model(model) or is_live_model):
            raise ValueError(
                "Model must be gemini-3.5-flash or newer (Gemini 3.5+), "
                f"got {model}"
            )
        import sys

        is_offline = (
            os.environ.get("TASK_STORE_MODE", "").strip().lower() == "fake"
            or "pytest" in sys.modules
        )
        # Vertex, an env Gemini key, or an explicit per-agent key satisfies auth.
        if (
            llm is None
            and api_key is None
            and not is_offline
            and os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") != "true"
            and not os.environ.get("GOOGLE_API_KEY")
        ):
            raise ValueError(
                "Set GOOGLE_GENAI_USE_VERTEXAI=true or provide GOOGLE_API_KEY"
            )

        self.model = model
        self.location = location
        self.speech_settings = speech_settings
        # Settings can replace the base prompt; chat.py points this at the store.
        self.prompt_source: Callable[[], str] = lambda: LIFE_PROMPT
        # The user's preferred name; chat.py points this at the store too.
        self.name_source: Callable[[], str] = lambda: "User"
        self._store: ContextVar[TaskStore] = ContextVar("life_task_store")
        # Set per live session: organizer, channel_store, channel_id, notify,
        # send (raw frame sender), and run_automation (name -> coroutine).
        self._bridge: ContextVar[dict | None] = ContextVar("life_bridge", default=None)
        self._instruction: ContextVar[str] = ContextVar(
            "life_instruction", default=LIFE_PROMPT
        )
        # Fire-and-forget handoffs keep the voice snappy; hold refs so the
        # tasks survive until they finish.
        self._pending: set[asyncio.Task] = set()

        self.agent = LlmAgent(
            name="life_companion",
            model=llm or _model_backend(model, api_key),
            instruction=self._instruction_for_turn,
            tools=self._build_tools(),
            generate_content_config=types.GenerateContentConfig(temperature=0.6),
        )
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            app_name=APP_NAME,
            agent=self.agent,
            session_service=self.session_service,
        )

    def _instruction_for_turn(self, _context) -> str:
        return self._instruction.get()

    def _spawn(self, coroutine) -> None:
        task = asyncio.ensure_future(coroutine)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def _build_tools(self) -> list[Callable]:
        def list_tasks(status: str | None = None) -> dict:
            """Read the user's tasks, optionally filtered by exact Status."""
            return {
                "tasks": [
                    _task_dict(task) for task in self._store.get().list_tasks(status)
                ]
            }

        def search_tasks(query: str) -> dict:
            """Find tasks whose Name or Notes contain the query text."""
            return {
                "tasks": [
                    _task_dict(task) for task in self._store.get().search_tasks(query)
                ]
            }

        def read_task_details(task_id: str) -> dict:
            """Read a task's details page body (markdown)."""
            return {
                "task_id": task_id,
                "details": self._store.get().get_task_body(task_id),
            }

        def read_task_comments(task_id: str) -> dict:
            """Read the comments on a task."""
            return {
                "task_id": task_id,
                "comments": self._store.get().list_comments(task_id),
            }

        def web_search(query: str) -> dict:
            """Answer any question about the world — facts, news, weather,
            prices, anything not on the board — with a quick Google search.

            Args:
                query: The user's question, in their own words and language.
            """
            bridge = self._bridge.get(None)
            if not bridge or "organizer" not in bridge:
                return {"error": "Search is not available in this session."}
            return bridge["organizer"]._web_answer(query)

        async def send_task_to_chat(instruction: str) -> dict:
            """Hand anything the user wants done or asked to the task assistant.

            Waits a moment for the reply: an `answer` comes back when it is
            quick, otherwise `answer_pending` and it lands in the chat.

            Args:
                instruction: One clear written instruction or question; it
                    lands in the chat and the task assistant handles it.
            """
            bridge = self._bridge.get()
            if not bridge:
                return {
                    "delivered": False,
                    "reason": "The chat bridge is not available in this session.",
                }
            task_store = self._store.get()
            outcome = {"text": "", "error": ""}

            async def hand_off() -> None:
                try:
                    async for chunk in bridge["organizer"].chat(
                        instruction,
                        bridge["channel_store"],
                        task_store,
                        bridge["channel_id"],
                        timezone=bridge.get("timezone"),
                    ):
                        if "text" in chunk:
                            outcome["text"] = chunk["text"]
                        if "error" in chunk:
                            outcome["error"] = chunk["error"]
                finally:
                    await bridge["notify"]()
                    # A reply nobody is waiting for gets pushed into the live
                    # session, so the navigator speaks it without being asked.
                    push = bridge.get("push_text")
                    answer = outcome["text"] or (
                        f"It failed: {outcome['error']}" if outcome["error"] else ""
                    )
                    if push and answer and outcome.get("push") and not outcome.get("awaited"):
                        push(f"[the task assistant replied] {answer}")

            task = asyncio.ensure_future(hand_off())
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
            bridge["last_handoff"] = (task, outcome)
            # The turn has started and persisted the instruction: show it now.
            await asyncio.sleep(0)
            await bridge["notify"]()
            try:
                # A short beat: quick answers get read back to the user directly.
                await asyncio.wait_for(asyncio.shield(task), timeout=QUICK_WAIT_SECONDS)
            except asyncio.TimeoutError:
                outcome["push"] = True
                return {
                    "delivered": True,
                    "answer_pending": True,
                    "note": "Still working; the reply will be pushed to you — "
                    "speak it to the user when it arrives.",
                }
            if outcome["error"]:
                return {"delivered": False, "reason": outcome["error"]}
            return {"delivered": True, "answer": outcome["text"]}

        async def wait_for_chat_answer() -> dict:
            """Wait for the task assistant to finish the last handoff.

            Returns its answer so it can be spoken back; after a long wait
            it reports pending and the reply lands in the chat instead.
            """
            bridge = self._bridge.get()
            handoff = (bridge or {}).get("last_handoff")
            if not handoff:
                return {"answer": "", "note": "Nothing was handed to the chat yet."}
            task, outcome = handoff
            outcome["awaited"] = True
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=LONG_WAIT_SECONDS)
            except asyncio.TimeoutError:
                return {
                    "answer_pending": True,
                    "note": "Still working; the reply will appear in the chat.",
                }
            if outcome["error"]:
                return {"delivered": False, "reason": outcome["error"]}
            return {"answer": outcome["text"]}

        async def navigate(target: str) -> dict:
            """Move the app to a place from the app map.

            Args:
                target: "chat", "settings", or an automation id from the map.
            """
            bridge = self._bridge.get()
            if not bridge:
                return {"navigated": False, "reason": "No app to navigate in this session."}
            await bridge["send"]({"type": "navigate", "target": target.strip()})
            return {"navigated": target.strip()}

        async def run_automation(automation: str) -> dict:
            """Start an automation now, by its name or id from the app map.

            Args:
                automation: The automation's name or id.
            """
            bridge = self._bridge.get()
            if not bridge:
                return {"started": False, "reason": "No automations in this session."}
            return await bridge["run_automation"](automation.strip())

        tools = [
            list_tasks,
            search_tasks,
            read_task_details,
            read_task_comments,
            web_search,
            send_task_to_chat,
            wait_for_chat_answer,
            navigate,
            run_automation,
        ]
        # A failing tool answers the model instead of tearing down the live
        # session — same contract as the organizer's board tools.
        return [_shielded(tool) for tool in tools]

    async def _new_session(self, messages: list[Message]):
        session = await self.session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=f"turn-{uuid.uuid4()}",
        )
        for item in ContextWindow.get_model_input(messages):
            role = "user" if item["role"] == "user" else "model"
            author = "user" if role == "user" else self.agent.name
            await self.session_service.append_event(
                session=session,
                event=Event(
                    author=author,
                    content=types.Content(
                        role=role, parts=[types.Part(text=item["content"])]
                    ),
                ),
            )
        return session

    async def chat(
        self,
        user_message: str,
        channel_store: ChannelStore,
        task_store: TaskStore,
        channel_id: str,
    ) -> AsyncGenerator[dict, None]:
        """Run one turn and persist the visible transcript."""
        existing = channel_store.get_channel(channel_id)
        store_token = self._store.set(task_store)
        try:
            session = await self._new_session(existing)
            model_text = ""
            tool_calls: list[dict] = []
            tool_results: list[dict] = []
            async for event in self.runner.run_async(
                user_id=USER_ID,
                session_id=session.id,
                new_message=types.Content(
                    role="user", parts=[types.Part(text=user_message)]
                ),
            ):
                for call in event.get_function_calls():
                    tool_calls.append({"name": call.name, "args": dict(call.args or {})})
                    yield {"tool": call.name, "status": "started"}
                for response in event.get_function_responses():
                    tool_results.append({"name": response.name, "response": response.response})
                    yield {"tool": response.name, "status": "completed"}
                if event.content and event.content.parts:
                    text_parts = [
                        part.text
                        for part in event.content.parts
                        if part.text and not part.thought
                    ]
                    if text_parts and event.is_final_response():
                        model_text = "".join(text_parts)

            answer = model_text.strip() or "Done."
            channel_store.append_message(
                channel_id,
                Message("user", user_message, time.time(), tool_calls=tool_calls),
            )
            channel_store.append_message(
                channel_id,
                Message("assistant", answer, time.time(), tool_results=tool_results),
            )
            yield {"text": answer}
            yield {"done": True}
        except Exception as exc:
            yield {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            self._store.reset(store_token)

    def _speech_config(self):
        """Build the session voice/accent from settings, or None for defaults."""
        speech = (self.speech_settings() if self.speech_settings else None) or {}
        voice = speech.get("voice_name")
        language = speech.get("language_code")
        if not voice and not language:
            return None
        return types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
            if voice
            else None,
            language_code=language or None,
        )

    async def live_bridge(
        self,
        websocket,
        channel_store: ChannelStore,
        task_store: TaskStore,
        channel_id: str,
        timezone: str | None = None,
        organizer=None,
        app_map: str = "",
        automation_starter: Callable | None = None,
        recall: Callable | None = None,
        remember: Callable | None = None,
    ) -> None:
        """Bridge one browser WebSocket to a bidirectional live-audio session.

        Client frames: {type:"audio", data:<b64 pcm16@16k>} and {type:"end"}.
        Server frames: audio (b64 pcm16@24k), interrupted, turn_complete,
        chat_updated, error. The conversation is voice-only in the UI —
        nothing becomes chat bubbles — but finished turns are transcribed
        into a rolling voice memory (`remember`) that seeds the next
        session's instruction (`recall`), so follow-ups keep their context.
        """
        from google.adk.agents.live_request_queue import LiveRequestQueue
        from google.adk.agents.run_config import RunConfig, StreamingMode

        queue = LiveRequestQueue()
        run_config = RunConfig(
            response_modalities=["AUDIO"],
            streaming_mode=StreamingMode.BIDI,
            speech_config=self._speech_config(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )
        session = await self._new_session(channel_store.get_channel(channel_id))
        store_token = self._store.set(task_store)
        instruction = self.prompt_source() or LIFE_PROMPT
        memory_items = (recall() if recall else None) or []
        if memory_items:
            lines = ["Recent voice conversation (newest last):"]
            for item in memory_items:
                speaker = self.name_source() if item.get("role") == "user" else "You"
                lines.append(f"{speaker}: {item.get('content', '')}")
            instruction = f"{instruction}\n\n" + "\n".join(lines)
        if app_map:
            instruction = f"{instruction}\n\n{app_map}"
        instruction_token = self._instruction.set(instruction)

        # Per-turn transcription buffers. ADK yields deltas (finished=False)
        # and a final aggregated copy (finished=True) that replaces them.
        user_text: list[str] = []
        agent_text: list[str] = []

        def flush_memory() -> None:
            spoken = "".join(user_text).strip()
            answered = "".join(agent_text).strip()
            user_text.clear()
            agent_text.clear()
            if remember is None or not (spoken or answered):
                return
            entries = []
            if spoken:
                entries.append({"role": "user", "content": spoken})
            if answered:
                entries.append({"role": "assistant", "content": answered})
            try:
                remember(entries)
            except Exception:
                pass

        async def send_frame(frame: dict) -> None:
            try:
                await websocket.send_json(frame)
            except Exception:
                pass

        async def notify_chat_updated() -> None:
            await send_frame({"type": "chat_updated"})

        async def start_automation(name: str) -> dict:
            if automation_starter is None:
                return {"started": False, "reason": "Automations are unavailable."}
            return await automation_starter(name)

        def push_text(text: str) -> None:
            queue.send_content(
                types.Content(role="user", parts=[types.Part(text=text)])
            )

        bridge_token = self._bridge.set(
            {
                "organizer": organizer,
                "channel_store": channel_store,
                "channel_id": channel_id,
                "timezone": timezone,
                "notify": notify_chat_updated,
                "send": send_frame,
                "run_automation": start_automation,
                "push_text": push_text,
            }
            if organizer is not None
            else None
        )

        async def pump_client() -> None:
            while True:
                frame = await websocket.receive_json()
                kind = frame.get("type")
                if kind == "audio":
                    queue.send_realtime(
                        types.Blob(
                            data=base64.b64decode(frame.get("data", "")),
                            mime_type="audio/pcm;rate=16000",
                        )
                    )
                elif kind == "end":
                    return

        debug = os.environ.get("LIVE_DEBUG") == "1"
        if debug:
            _install_live_probes()

        async def pump_agent() -> None:
            async for event in self.runner.run_live(
                user_id=USER_ID,
                session_id=session.id,
                live_request_queue=queue,
                run_config=run_config,
            ):
                if debug:
                    parts = event.content.parts if event.content and event.content.parts else []
                    print(
                        "LIVE_EVT",
                        {
                            "inline": [
                                f"{p.inline_data.mime_type}:{len(p.inline_data.data or b'')}"
                                for p in parts
                                if p.inline_data
                            ],
                            "text": bool([p for p in parts if p.text]),
                            "in_t": bool(event.input_transcription),
                            "out_t": bool(event.output_transcription),
                            "tc": event.turn_complete,
                            "int": event.interrupted,
                            "partial": event.partial,
                        },
                        flush=True,
                    )
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.inline_data and part.inline_data.data:
                            await websocket.send_json(
                                {
                                    "type": "audio",
                                    "data": base64.b64encode(
                                        part.inline_data.data
                                    ).decode(),
                                }
                            )
                if event.input_transcription and event.input_transcription.text:
                    if event.input_transcription.finished:
                        user_text[:] = [event.input_transcription.text]
                    else:
                        user_text.append(event.input_transcription.text)
                if event.output_transcription and event.output_transcription.text:
                    if event.output_transcription.finished:
                        agent_text[:] = [event.output_transcription.text]
                    else:
                        agent_text.append(event.output_transcription.text)
                if event.interrupted:
                    await websocket.send_json({"type": "interrupted"})
                if event.turn_complete:
                    flush_memory()
                    await websocket.send_json({"type": "turn_complete"})

        client_task = asyncio.ensure_future(pump_client())
        agent_task = asyncio.ensure_future(pump_agent())
        try:
            done, _ = await asyncio.wait(
                {client_task, agent_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                exc = task.exception()
                if exc is not None:
                    raise exc
        except Exception as exc:
            try:
                await websocket.send_json(
                    {"type": "error", "message": f"{type(exc).__name__}: {exc}"}
                )
            except Exception:
                pass
        finally:
            for task in (client_task, agent_task):
                task.cancel()
            queue.close()
            flush_memory()
            self._instruction.reset(instruction_token)
            self._bridge.reset(bridge_token)
            self._store.reset(store_token)
