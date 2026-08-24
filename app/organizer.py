"""Avi's one Google ADK LlmAgent and its four Notion task tools."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime
from functools import wraps
import re
import time
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
from app.knowledge import OrganizerKnowledge
from app.task_planning import (
    ANYWHERE,
    DEFAULT_MINUTES,
    DayPlanner,
    TaskFieldWriter,
    friendly_when,
    infer_when,
    local_now,
)
from app.task_store import Task, TaskStore


SYSTEM_PROMPT = """You are Avi's assistant. He talks naturally; you organize and keep his notes and tasks in Notion, say what you wrote, and never do the task itself. Capture first. Ask at most one useful question per item, usually When. If he answers, update the item. If he is vague or moves on, keep the default, state it once, and never ask again.

Defaults: Status=Not started; Place=Anywhere; Minutes=30; Notes=his words; When=explicit time, today for today/now/tonight/urgent, tomorrow for a plain reminder, empty for a someday idea. Always state the applied defaults briefly."""

APP_NAME = "taskmaker"
USER_ID = "avi"
NOT_STARTED = "Not started"
_VAGUE = {
    "whatever",
    "you decide",
    "dunno",
    "don't know",
    "dont know",
    "doesn't matter",
    "doesnt matter",
    "no preference",
    "up to you",
}
_AUTOMATION_CHANNEL_PREFIX = "automation-"
_BOARD_TOOL_REFUSAL = (
    "Board tools are unavailable in automation channels. Continue this "
    "automation using only its supplied context; do not retry a board tool."
)


def _task_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "name": task.title,
        "status": task.status,
        "when": task.when,
        "place": task.place,
        "minutes": task.minutes,
        "notes": task.notes,
    }


class TaskOrganizerAgent:
    """A thin runner around exactly one real ADK ``LlmAgent``."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-3.5-flash",
        location: str = "global",
        *,
        llm: BaseLlm | None = None,
        clock: Callable[[], datetime] | None = None,
        knowledge: OrganizerKnowledge | None = None,
    ) -> None:
        if location != "global":
            raise ValueError(
                f"Location must be 'global' for contest eligibility, got {location}"
            )
        if model != "gemini-3.5-flash":
            raise ValueError(
                "Model must be 'gemini-3.5-flash' for contest eligibility "
                f"(Gemini 3.5+), got {model}"
            )

        self.api_key = api_key
        self.model = model
        self.location = location
        self.clock = clock
        self.knowledge = knowledge
        self._store: ContextVar[TaskStore] = ContextVar("task_store")
        self._message: ContextVar[str] = ContextVar("user_message", default="")
        self._channel_id: ContextVar[str | None] = ContextVar(
            "organizer_channel_id", default=None
        )
        self._created: ContextVar[list[Task]] = ContextVar("created_tasks")
        self._updated: ContextVar[list[Task]] = ContextVar("updated_tasks")
        self._instruction: ContextVar[str] = ContextVar(
            "organizer_instruction", default=SYSTEM_PROMPT
        )
        self.day_planner: DayPlanner | None = None
        self._save_sweep: Callable[[dict], None] | None = None

        tools = self._build_tools()
        self.agent = LlmAgent(
            name="task_organizer",
            model=llm or model,
            instruction=self._instruction_for_turn,
            tools=tools,
            generate_content_config=types.GenerateContentConfig(temperature=0.2),
        )
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            app_name=APP_NAME,
            agent=self.agent,
            session_service=self.session_service,
        )

    def configure_planning(
        self, planner: DayPlanner, save_sweep: Callable[[dict], None]
    ) -> None:
        self.day_planner = planner
        self._save_sweep = save_sweep

    def _build_tools(self) -> list[Callable]:
        def create_task(
            title: str,
            when: str | None = None,
            place: str | None = None,
            minutes: int | None = None,
            notes: str | None = None,
            status: str = NOT_STARTED,
        ) -> dict:
            """Write a task immediately. Omit fields to apply Avi's defaults.

            Args:
                title: Short task or reminder name.
                when: ISO date/datetime, today/tomorrow, or empty for no date.
                place: Where it can be done.
                minutes: Rough duration.
                notes: Avi's wording or useful detail.
                status: Not started, In progress, or Done.
            """
            message = self._message.get()
            task = self._store.get().create_task(
                title=title.strip(),
                lane=status,
                when=infer_when(message, when, self.clock),
                place=(place or ANYWHERE).strip() or ANYWHERE,
                minutes=DEFAULT_MINUTES if minutes is None else minutes,
                notes=(notes or message or title).strip(),
            )
            self._created.get().append(task)
            return {"created": _task_dict(task)}

        def rename_task(task_id: str, new_title: str) -> dict:
            """Rename one task found on Avi's task board."""
            task = self._store.get().rename_task(task_id, new_title)
            self._updated.get().append(task)
            return {"renamed": _task_dict(task)}

        def move_task(
            task_id: str,
            status: str | None = None,
            when: str | None = None,
            place: str | None = None,
            minutes: int | None = None,
            notes: str | None = None,
        ) -> dict:
            """Correct an existing task's status, date, place, size, or notes."""
            store = self._store.get()
            changed = False
            task: Task | None = None
            if status is not None:
                task = store.move_task(task_id, status)
                changed = True
            optional = {}
            if when is not None:
                optional["when"] = infer_when(self._message.get(), when, self.clock)
            if place is not None:
                optional["place"] = place
            if minutes is not None:
                optional["minutes"] = minutes
            if notes is not None:
                optional["notes"] = notes
            if optional:
                task = TaskFieldWriter(store).update(task_id, **optional)
                changed = True
            if not changed:
                raise ValueError("Give at least one task field to change")
            assert task is not None
            self._updated.get().append(task)
            return {"updated": _task_dict(task)}

        def list_tasks(status: str | None = None) -> dict:
            """Read Avi's tasks, optionally filtered by exact Status."""
            return {
                "tasks": [
                    _task_dict(task) for task in self._store.get().list_tasks(status)
                ]
            }

        return [
            self._gate_board_tool(tool)
            for tool in (create_task, rename_task, move_task, list_tasks)
        ]

    def _gate_board_tool(self, tool: Callable) -> Callable:
        """Refuse every board tool unless its current channel is known and safe."""

        @wraps(tool)
        def guarded(*args, **kwargs):
            channel_id = self._channel_id.get()
            if (
                not isinstance(channel_id, str)
                or not channel_id
                or channel_id.startswith(_AUTOMATION_CHANNEL_PREFIX)
            ):
                return {"refused": True, "reason": _BOARD_TOOL_REFUSAL}
            return tool(*args, **kwargs)

        return guarded

    def _instruction_for_turn(self, _context) -> str:
        """Resolve the one cached instruction string for the current ADK turn."""
        return self._instruction.get()

    def get_instruction(
        self,
        task_store: TaskStore | None = None,
        query: str = "",
    ) -> str:
        """Assemble one instruction from the short prompt and retrieved knowledge."""
        del task_store  # Board state is available only through the four board tools.
        context = self.knowledge.instruction_context(query) if self.knowledge else ""
        return f"{SYSTEM_PROMPT}{context}"

    def get_config(self) -> dict:
        """Return observed runtime values and fail if eligibility has drifted."""
        framework = "Google ADK" if isinstance(self.agent, LlmAgent) else type(self.agent).__name__
        violations = []
        if self.model != "gemini-3.5-flash":
            violations.append(f"model={self.model!r}")
        if self.location != "global":
            violations.append(f"location={self.location!r}")
        if framework != "Google ADK":
            violations.append(f"framework={framework!r}")
        if violations:
            raise RuntimeError("Eligibility drift detected: " + ", ".join(violations))
        return {
            "agent_type": type(self.agent).__name__,
            "model": self.model,
            "location": self.location,
            "framework": framework,
        }

    @staticmethod
    def _is_vague(message: str) -> bool:
        normalized = re.sub(r"[^a-z' ]", "", message.casefold()).strip()
        return normalized in _VAGUE

    @staticmethod
    def _last_question(messages: list[Message]) -> Message | None:
        for message in reversed(messages):
            if message.role == "assistant":
                return message if "?" in message.content else None
        return None

    @staticmethod
    def _kept_default(previous: str) -> str:
        statement = previous.split("?", 1)[0].strip()
        match = re.search(r"Noted\s*[—-]\s*(.+?)(?:\.|$)", statement, re.I)
        if match:
            return f"Kept the default — {match.group(1).strip()}."
        return "Kept the default."

    @staticmethod
    def _at_most_one_question(text: str) -> str:
        first = text.find("?")
        if first < 0:
            return text.strip()
        second = text.find("?", first + 1)
        return (text if second < 0 else text[: first + 1]).strip()

    @staticmethod
    def _should_ask_when(message: str) -> bool:
        lowered = message.casefold()
        has_time = bool(
            re.search(
                r"\b(today|tomorrow|tonight|now|urgent|someday|at some point|"
                r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
                r"\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{4}-\d{2}-\d{2})\b",
                lowered,
            )
        )
        return lowered.lstrip().startswith("remind me") and not has_time

    def _confirmation(self, task: Task) -> str:
        now = local_now(self.clock)
        return (
            f"Noted — {friendly_when(task.when, now)}, "
            f"{task.place or ANYWHERE}, {int(task.minutes or DEFAULT_MINUTES)} min."
        )

    def _final_text(
        self, user_message: str, created: list[Task], model_text: str
    ) -> str:
        if created:
            lines = [self._confirmation(task) for task in created]
            if len(created) == 1 and self._should_ask_when(user_message):
                lines[-1] += " Would a specific time tomorrow help?"
            return "\n".join(lines)
        return self._at_most_one_question(model_text or "Done.")

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
        """Run one ADK turn and persist the visible transcript."""
        existing = channel_store.get_channel(channel_id)
        previous_question = self._last_question(existing)
        if previous_question and self._is_vague(user_message):
            answer = self._kept_default(previous_question.content)
            channel_store.append_message(channel_id, Message("user", user_message, time.time()))
            channel_store.append_message(channel_id, Message("assistant", answer, time.time()))
            yield {"text": answer}
            yield {"done": True}
            return

        if self.day_planner is not None:
            place = self.day_planner.extract_place(user_message)
            if place is not None:
                sweep = self.day_planner.build(place)
                sweep["channel_id"] = channel_id
                if self._save_sweep:
                    self._save_sweep(sweep)
                channel_store.append_message(
                    channel_id, Message("user", user_message, time.time())
                )
                channel_store.append_message(
                    channel_id, Message("assistant", sweep["text"], time.time())
                )
                yield {"text": sweep["text"], "controls": sweep["controls"]}
                yield {"done": True}
                return

        store_token = self._store.set(task_store)
        message_token = self._message.set(user_message)
        channel_token = self._channel_id.set(channel_id)
        created_token = self._created.set([])
        updated_token = self._updated.set([])
        instruction_token = self._instruction.set(
            self.get_instruction(task_store, query=user_message)
        )
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
                calls = event.get_function_calls()
                responses = event.get_function_responses()
                for call in calls:
                    tool_calls.append({"name": call.name, "args": dict(call.args or {})})
                    yield {"tool": call.name, "status": "started"}
                for response in responses:
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

            created = list(self._created.get())
            answer = self._final_text(user_message, created, model_text)
            channel_store.append_message(
                channel_id,
                Message("user", user_message, time.time(), tool_calls=tool_calls),
            )
            channel_store.append_message(
                channel_id,
                Message(
                    "assistant",
                    answer,
                    time.time(),
                    tool_results=tool_results,
                ),
            )
            yield {"text": answer}
            yield {"done": True}
        except Exception as exc:
            yield {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            self._instruction.reset(instruction_token)
            self._updated.reset(updated_token)
            self._created.reset(created_token)
            self._channel_id.reset(channel_token)
            self._message.reset(message_token)
            self._store.reset(store_token)

    def _knowledge(self) -> OrganizerKnowledge:
        if self.knowledge is None:
            raise RuntimeError("knowledge service is not configured")
        return self.knowledge

    def create_skill(self, name: str, content: str, change_summary: str) -> str:
        """Create one atomic skill through this organizer's private knowledge service."""
        return self._knowledge().create_skill(name, content, change_summary)

    def record_rule(
        self,
        name: str,
        content: str,
        change_summary: str,
        *,
        explicit_avi_instruction: bool,
    ) -> str:
        return self._knowledge().record_rule(
            name,
            content,
            change_summary,
            explicit_avi_instruction=explicit_avi_instruction,
        )

    def dream_skill(self, name: str, observation: str, change_summary: str) -> str:
        return self._knowledge().dream_skill(name, observation, change_summary)

    def consolidate_skill(self, name: str, change_summary: str | None = None) -> dict:
        return self._knowledge().consolidate_skill(name, change_summary)

    def get_learning_log(self) -> list[dict]:
        """Return the complete private log in-process; no HTTP route exposes it."""
        return self._knowledge().get_learning_log()
