"""Avi's life companion agent: open chat, read-only board access, web research.

One second ADK ``LlmAgent`` beside the task organizer. It never mutates the
board — it holds only read tools — and gains Google Search through a
``web_research`` sub-agent wrapped as an ``AgentTool`` (Gemini cannot mix the
built-in search grounding with function tools in a single agent).
"""
from __future__ import annotations

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


LIFE_PROMPT = """You are Avi's life assistant: a warm, sharp companion he can talk with about anything — his day, ideas, questions, the world.

You can read his Notion task board with the board tools to answer questions about what is on it. You can never create, change, or delete anything there; if he wants a change, point him to the Task chat.

For current events, facts you are not sure of, or anything worth looking up, call web_research. For a bigger question, let it run a deeper search and then summarize what it found, naming the sources. Keep answers conversational and concise unless he asks for depth."""

APP_NAME = "life"


class LifeAgent:
    """A thin runner around one read-only, search-capable ADK ``LlmAgent``."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        location: str = "global",
        *,
        llm: BaseLlm | None = None,
    ) -> None:
        if location != "global":
            raise ValueError(f"Location must be 'global', got {location}")
        if not _eligible_model(model):
            raise ValueError(
                "Model must be gemini-3.5-flash or newer (Gemini 3.5+), "
                f"got {model}"
            )
        import sys

        is_offline = (
            os.environ.get("TASK_STORE_MODE", "").strip().lower() == "fake"
            or "pytest" in sys.modules
        )
        if llm is None and not is_offline and os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") != "true":
            raise ValueError(
                "GOOGLE_GENAI_USE_VERTEXAI must be set to 'true', "
                f"got {os.environ.get('GOOGLE_GENAI_USE_VERTEXAI')!r}"
            )

        self.model = model
        self.location = location
        self._store: ContextVar[TaskStore] = ContextVar("life_task_store")

        web_agent = LlmAgent(
            name="web_research",
            model=llm or model,
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

        return [list_tasks, search_tasks, read_task_details, read_task_comments]

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
