"""Avi's one Google ADK LlmAgent and its gated board and planning tools."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from inspect import iscoroutinefunction
import os
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
from app.task_planning import TaskFieldWriter, infer_when, recent_places
from app.task_store import Task, TaskStore


SYSTEM_PROMPT = """You are Avi's assistant. He talks; you organize his Notion task board and keep it in order. You never do the task itself, and questions or conversation are not tasks.

Reply in one short line. "Added Grocery list." is a complete answer. Do not list the fields you set, do not explain a default, do not repeat his message back to him. He wants to glance at the reply and move on. Ask a question only when the task is unusable without it, and then ask exactly one.

A property is only worth having if he can sort or filter on it, so fill one in only when Avi actually gave it:
- When: a real date, and only when he chose a day. Having no date is normal and correct — leave it empty rather than guess one.
- Place: whatever he names; new values are fine. Empty when he did not say where.
- Minutes: a number he indicated. Empty when he did not.
Anything free-form — his own wording, context, a link, a longer description — belongs on the task's own page, through `details` when you create it or `write_task_details` afterwards. Never squeeze prose into a property.

Use the board freely: search before creating something that may already exist, rename, correct, delete what he cancels and restore it if he changes his mind, and comment when context belongs beside a task.

He can also ask you to run one of his automations by name: `list_automations` shows what exists and what each one does, `run_automation` runs one now."""

DEFAULT_MODEL = "gemini-3.7-flash"
_MODEL_FAMILY = re.compile(r"^gemini-(\d+)\.(\d+)")


def _eligible_model(model: str) -> bool:
    family = _MODEL_FAMILY.match(model)
    return family is not None and (
        int(family.group(1)),
        int(family.group(2)),
    ) >= (3, 5)


def _model_backend(model: str, api_key: str | None):
    """The model reference for an agent: a plain id (env credentials — Vertex
    or GOOGLE_API_KEY), or a Gemini bound to one explicit API key so that
    per-device keys never touch process-global state."""
    if not api_key:
        return model
    from google.adk.models.google_llm import Gemini

    return Gemini(model=model, client_kwargs={"api_key": api_key, "vertexai": False})

APP_NAME = "taskmaker"
USER_ID = "avi"
NOT_STARTED = "Not started"
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
        model: str = DEFAULT_MODEL,
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
        if not _eligible_model(model):
            raise ValueError(
                "Model must be gemini-3.5-flash or newer (Gemini 3.5+), "
                f"got {model}"
            )
        # Contest eligibility: production must use Vertex AI explicitly.
        # Offline/test mode (TASK_STORE_MODE=fake or pytest running) is exempt.
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
                "Set GOOGLE_GENAI_USE_VERTEXAI=true or provide GOOGLE_API_KEY, "
                f"got GOOGLE_GENAI_USE_VERTEXAI={os.environ.get('GOOGLE_GENAI_USE_VERTEXAI')!r}"
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
        self._planned: ContextVar[list[dict]] = ContextVar("planned_days")
        self._instruction: ContextVar[str] = ContextVar(
            "organizer_instruction", default=SYSTEM_PROMPT
        )
        # Settings can replace the base prompt; chat.py points this at the store.
        self.prompt_source: Callable[[], str] = lambda: SYSTEM_PROMPT
        self.automations = None  # set by chat.py so Avi can trigger them by name

        tools = self._build_tools()
        self.agent = LlmAgent(
            name="task_organizer",
            model=llm or _model_backend(model, api_key),
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

    def configure_automations(self, runner) -> None:
        self.automations = runner

    def _build_tools(self) -> list[Callable]:
        def create_task(
            title: str,
            when: str | None = None,
            place: str | None = None,
            minutes: int | None = None,
            details: str = "",
            status: str = NOT_STARTED,
        ) -> dict:
            """Write a task immediately. Leave a field out rather than guess it.

            Args:
                title: Short task or reminder name.
                when: ISO date/datetime, or today/tomorrow. Empty unless Avi
                    actually chose a day.
                place: Where it can be done; any value, new ones are fine.
                minutes: Rough duration as a number.
                details: Longer wording, which goes on the task's own page.
                status: Not started, In progress, or Done.
            """
            store = self._store.get()
            task = store.create_task(
                title=title.strip(),
                lane=status,
                when=infer_when(self._message.get(), when, self.clock),
                place=(place or "").strip() or None,
                minutes=minutes,
            )
            if details.strip():
                store.write_task_body(task.id, details.strip())
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

        def write_task_details(task_id: str, markdown: str, append: bool = False) -> dict:
            """Write longer material onto a task's details page.

            Args:
                task_id: The task to write to.
                markdown: Markdown body content.
                append: Add to the end instead of replacing the page body.
            """
            self._store.get().write_task_body(task_id, markdown, append=append)
            return {"task_id": task_id, "written": True}

        def delete_task(task_id: str) -> dict:
            """Archive a task Avi cancelled or no longer wants; restore_task undoes it."""
            task = self._store.get().delete_task(task_id)
            self._updated.get().append(task)
            return {"deleted": _task_dict(task)}

        def restore_task(task_id: str) -> dict:
            """Bring back a task deleted earlier in this conversation."""
            task = self._store.get().restore_task(task_id)
            self._updated.get().append(task)
            return {"restored": _task_dict(task)}

        def add_task_comment(task_id: str, text: str) -> dict:
            """Leave a short comment on a task for context worth keeping."""
            self._store.get().add_comment(task_id, text)
            return {"task_id": task_id, "commented": True}

        def read_task_comments(task_id: str) -> dict:
            """Read the comments on a task."""
            return {
                "task_id": task_id,
                "comments": self._store.get().list_comments(task_id),
            }

        def list_automations() -> dict:
            """List Avi's automations: what each is called and when it runs."""
            if self.automations is None:
                raise RuntimeError("Automations are not configured")
            return {
                "automations": [
                    {"name": item.name, "trigger": item.schedule, "does": item.prompt}
                    for item in self.automations.store.list()
                ]
            }

        async def run_automation(name: str) -> dict:
            """Run one of Avi's automations now, matched by its name.

            Args:
                name: The automation's name, or a distinctive part of it.
            """
            if self.automations is None:
                raise RuntimeError("Automations are not configured")
            wanted = name.strip().casefold()
            items = self.automations.store.list()
            match = next((item for item in items if item.name.casefold() == wanted), None)
            if match is None:
                partial = [item for item in items if wanted and wanted in item.name.casefold()]
                if len(partial) != 1:
                    # Say what exists rather than guess between two automations.
                    return {
                        "ran": False,
                        "reason": "no single automation matches that name",
                        "automations": [item.name for item in items],
                    }
                match = partial[0]
            result = await self.automations.run(match.id)
            return {"ran": True, "name": match.name, "text": result.get("text", "")}

        return [
            self._gate_board_tool(tool)
            for tool in (
                create_task,
                rename_task,
                move_task,
                list_tasks,
                search_tasks,
                read_task_details,
                write_task_details,
                delete_task,
                restore_task,
                add_task_comment,
                read_task_comments,
                list_automations,
                run_automation,
            )
        ]

    def _refusal(self) -> dict | None:
        channel_id = self._channel_id.get()
        if (
            not isinstance(channel_id, str)
            or not channel_id
            or channel_id.startswith(_AUTOMATION_CHANNEL_PREFIX)
        ):
            return {"refused": True, "reason": _BOARD_TOOL_REFUSAL}
        return None

    def _gate_board_tool(self, tool: Callable) -> Callable:
        """Refuse every board tool unless its current channel is known and safe."""

        if iscoroutinefunction(tool):
            @wraps(tool)
            async def guarded_async(*args, **kwargs):
                # An async tool has to stay async, or ADK is handed a coroutine
                # it never awaits and the call silently does nothing.
                return self._refusal() or await tool(*args, **kwargs)

            return guarded_async

        @wraps(tool)
        def guarded(*args, **kwargs):
            return self._refusal() or tool(*args, **kwargs)

        return guarded

    def _instruction_for_turn(self, _context) -> str:
        """Resolve the one cached instruction string for the current ADK turn."""
        return self._instruction.get()

    def get_instruction(
        self,
        task_store: TaskStore | None = None,
        query: str = "",
        include_board_state: bool = True,
    ) -> str:
        """Assemble one instruction from the short prompt and retrieved knowledge."""
        place_hint = ""
        if task_store is not None and include_board_state:
            places = recent_places(task_store)
            place_hint = f" Current Place values on Avi's board: {', '.join(places)}."
        context = self.knowledge.instruction_context(query) if self.knowledge else ""
        return f"{self.prompt_source()}{place_hint}{context}"

    def get_config(self) -> dict:
        """Return observed runtime values and fail if eligibility has drifted."""
        framework = "Google ADK" if (type(self.agent).__module__.startswith("google.adk.agents") and type(self.agent).__name__ == "LlmAgent") else type(self.agent).__name__
        violations = []
        if not _eligible_model(self.model):
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

    def _confirmation(self, task: Task) -> str:
        return f"Added {task.title}."

    def _final_text(
        self, user_message: str, created: list[Task], model_text: str
    ) -> str:
        # The model's own reply carries confirmations and any clarifying
        # question; canned text only covers a turn that produced no text.
        if model_text.strip():
            return model_text.strip()
        if created:
            return "\n".join(self._confirmation(task) for task in created)
        return "Done."

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
        attachments: list[tuple[str, bytes]] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Run one ADK turn and persist the visible transcript."""
        existing = channel_store.get_channel(channel_id)
        store_token = self._store.set(task_store)
        message_token = self._message.set(user_message)
        channel_token = self._channel_id.set(channel_id)
        created_token = self._created.set([])
        updated_token = self._updated.set([])
        planned_token = self._planned.set([])
        instruction_token = self._instruction.set(
            self.get_instruction(
                task_store,
                query=user_message,
                include_board_state=not channel_id.startswith(
                    _AUTOMATION_CHANNEL_PREFIX
                ),
            )
        )
        try:
            session = await self._new_session(existing)
            model_text = ""
            tool_calls: list[dict] = []
            tool_results: list[dict] = []
            message_parts = [types.Part(text=user_message)]
            for mime_type, blob in attachments or []:
                message_parts.append(
                    types.Part(
                        inline_data=types.Blob(mime_type=mime_type, data=blob)
                    )
                )
            async for event in self.runner.run_async(
                user_id=USER_ID,
                session_id=session.id,
                new_message=types.Content(role="user", parts=message_parts),
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
            updated = list(self._updated.get())
            planned = list(self._planned.get())
            answer = self._final_text(user_message, created, model_text)
            if planned:
                answer = (
                    f"{answer}\n\n{planned[-1]['text']}"
                    if created or updated
                    else planned[-1]["text"]
                )
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
            response = {"text": answer}
            if planned:
                response["controls"] = planned[-1]["controls"]
            yield response
            yield {"done": True}
        except Exception as exc:
            yield {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            self._instruction.reset(instruction_token)
            self._planned.reset(planned_token)
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
