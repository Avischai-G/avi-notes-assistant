"""Avi's life companion agent: open chat, read-only board access, web research.

One second ADK ``LlmAgent`` beside the task organizer. It never mutates the
board — it holds only read tools — and gains Google Search through a
``web_research`` sub-agent wrapped as an ``AgentTool`` (Gemini cannot mix the
built-in search grounding with function tools in a single agent).
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
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from app.channel_store import ChannelStore, Message
from app.context_window import ContextWindow
from app.organizer import DEFAULT_MODEL, USER_ID, _eligible_model, _task_dict
from app.task_store import TaskStore


LIFE_PROMPT = """You are Avi's live voice companion: warm, sharp, and spoken. Talk with him about anything — his day, ideas, questions, the world.

You can look at his Notion task board with the board tools to answer questions about what is on it, but you can never change it yourself. When he wants anything created, changed, or removed on the board, call send_task_to_chat with one clear written instruction describing exactly what he wants; the task assistant in the chat does the work. Then tell him briefly what you handed over. Never claim you edited the board.

For current events or anything worth looking up, call web_research and summarize what it found.

You are a voice, not a writer: keep replies short, natural, and speakable — no markdown, no bullet lists, no URLs read aloud."""

APP_NAME = "life"


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
    """A thin runner around one read-only, search-capable ADK ``LlmAgent``."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        location: str = "global",
        *,
        llm: BaseLlm | None = None,
        research_model: str = DEFAULT_MODEL,
        speech_settings: Callable[[], dict] | None = None,
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
        # Either Vertex or a user-supplied Gemini API key satisfies auth.
        if (
            llm is None
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
        self._store: ContextVar[TaskStore] = ContextVar("life_task_store")
        # Set per live session: {"organizer", "channel_store", "channel_id", "notify"}.
        self._bridge: ContextVar[dict | None] = ContextVar("life_bridge", default=None)

        web_agent = LlmAgent(
            name="web_research",
            model=llm or research_model,
            instruction=(
                "You are a web research assistant. Use Google Search to find "
                "current, reliable information for the request. Return a "
                "concise summary of what you found with the source names and "
                "links."
            ),
            tools=[google_search],
        )
        self.agent = LlmAgent(
            name="life_companion",
            model=llm or model,
            instruction=LIFE_PROMPT,
            tools=[*self._build_tools(), AgentTool(agent=web_agent)],
            generate_content_config=types.GenerateContentConfig(temperature=0.6),
        )
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            app_name=APP_NAME,
            agent=self.agent,
            session_service=self.session_service,
        )

    def _build_tools(self) -> list[Callable]:
        def list_tasks(status: str | None = None) -> dict:
            """Read Avi's tasks, optionally filtered by exact Status."""
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

        async def send_task_to_chat(instruction: str) -> dict:
            """Hand a board change Avi asked for to the task assistant in the chat.

            Args:
                instruction: One clear written instruction describing exactly
                    what to create, change, or remove on the board.
            """
            bridge = self._bridge.get()
            if not bridge:
                return {
                    "delivered": False,
                    "reason": "The chat bridge is not available in this session.",
                }
            answer = ""
            async for chunk in bridge["organizer"].chat(
                instruction,
                bridge["channel_store"],
                self._store.get(),
                bridge["channel_id"],
            ):
                if "text" in chunk:
                    answer = chunk["text"]
                if "error" in chunk:
                    return {"delivered": False, "reason": chunk["error"]}
            await bridge["notify"]()
            return {"delivered": True, "task_agent_reply": answer}

        return [
            list_tasks,
            search_tasks,
            read_task_details,
            read_task_comments,
            send_task_to_chat,
        ]

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
        organizer=None,
    ) -> None:
        """Bridge one browser WebSocket to a bidirectional live-audio session.

        Client frames: {type:"audio", data:<b64 pcm16@16k>} and {type:"end"}.
        Server frames: audio (b64 pcm16@24k), interrupted, turn_complete,
        chat_updated, error. The conversation is voice-only — nothing is
        persisted or shown as chat bubbles; board changes reach the chat
        through the send_task_to_chat tool, which runs the task organizer.
        """
        from google.adk.agents.live_request_queue import LiveRequestQueue
        from google.adk.agents.run_config import RunConfig, StreamingMode

        queue = LiveRequestQueue()
        run_config = RunConfig(
            response_modalities=["AUDIO"],
            streaming_mode=StreamingMode.BIDI,
            speech_config=self._speech_config(),
        )
        session = await self._new_session(channel_store.get_channel(channel_id))
        store_token = self._store.set(task_store)

        async def notify_chat_updated() -> None:
            try:
                await websocket.send_json({"type": "chat_updated"})
            except Exception:
                pass

        bridge_token = self._bridge.set(
            {
                "organizer": organizer,
                "channel_store": channel_store,
                "channel_id": channel_id,
                "notify": notify_chat_updated,
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
                if event.interrupted:
                    await websocket.send_json({"type": "interrupted"})
                if event.turn_complete:
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
            self._bridge.reset(bridge_token)
            self._store.reset(store_token)
