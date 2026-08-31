"""Acceptance tests for what a task gets, and what the organiser reports."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from app.automations import AutomationRunner, LocalAutomationStore, ORGANIZE_TASKS
from app.channel_store import LocalChannelStore
from app.organizer import SYSTEM_PROMPT, TaskOrganizerAgent
from app.task_planning import infer_when, next_trigger
from app.task_store import FakeTaskStore


class ScriptedToolLlm(BaseLlm):
    """One configured tool call followed by one ordinary model response."""

    tool_name: str = "create_task"
    tool_args: dict = {"title": "Call the accountant"}
    _calls: int = PrivateAttr(default=0)

    @property
    def calls(self) -> int:
        return self._calls

    async def generate_content_async(self, llm_request, stream=False):
        self._calls += 1
        if self._calls == 1:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name=self.tool_name,
                                args=self.tool_args,
                            )
                        )
                    ],
                ),
                partial=False,
            )
        else:
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text="Saved it.")]
                ),
                partial=False,
            )


async def _turn(agent, message, channels, tasks, channel_id="task-chat"):
    chunks = []
    async for chunk in agent.chat(message, channels, tasks, channel_id):
        chunks.append(chunk)
    return chunks


def _fixed_now():
    return datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def test_prompt_is_short_and_every_tool_is_gated():
    agent = TaskOrganizerAgent(
        api_key="offline",
        llm=ScriptedToolLlm(model="gemini-3.5-flash"),
    )
    assert len(SYSTEM_PROMPT.split()) <= 470
    assert [tool.__name__ for tool in agent.agent.tools] == [
        "create_task",
        "rename_task",
        "move_task",
        "list_tasks",
        "search_tasks",
        "read_task_details",
        "write_task_details",
        "set_task_checkbox",
        "attach_files_to_task",
        "set_task_reminder",
        "delete_task",
        "restore_task",
        "add_task_comment",
        "read_task_comments",
        "web_search",
        "notify",
        "remember",
        "clear_memory",
        "list_automations",
        "run_automation",
    ]


def test_bare_reminder_is_captured_before_question_with_stated_defaults():
    tasks = FakeTaskStore()
    channels = LocalChannelStore()
    channels.ensure_channel("task-chat")
    agent = TaskOrganizerAgent(
        api_key="offline",
        llm=ScriptedToolLlm(model="gemini-3.5-flash"),
        clock=_fixed_now,
    )

    chunks = asyncio.run(
        _turn(
            agent,
            "Remind me to call the accountant",
            channels,
            tasks,
        )
    )

    # Nothing is invented: a reminder with no day, place or size gets none of
    # them, because a guessed value is one the user cannot sort or filter on.
    [task] = tasks.list_tasks()
    assert task.title == "Call the accountant"
    assert task.status == "Not started"
    assert task.when is None
    assert task.place is None
    assert task.minutes is None
    # The model's own reply is the answer; nothing rewrites it.
    text = next(chunk["text"] for chunk in chunks if "text" in chunk)
    assert text == "Saved it."


def test_vague_answer_goes_to_the_model_and_writes_nothing_new():
    tasks = FakeTaskStore()
    channels = LocalChannelStore()
    channels.ensure_channel("task-chat")
    llm = ScriptedToolLlm(model="gemini-3.5-flash")
    agent = TaskOrganizerAgent(api_key="offline", llm=llm, clock=_fixed_now)
    asyncio.run(
        _turn(
            agent,
            "Remind me to call the accountant",
            channels,
            tasks,
        )
    )
    calls_after_capture = llm.calls

    chunks = asyncio.run(_turn(agent, "whatever", channels, tasks))

    # The prompt, not a regex shortcut, decides how to keep the default now.
    assert llm.calls == calls_after_capture + 1
    assert len(tasks.list_tasks()) == 1
    text = next(chunk["text"] for chunk in chunks if "text" in chunk)
    assert text == "Saved it."


def test_attachments_reach_the_model_as_inline_parts():
    class CapturingLlm(ScriptedToolLlm):
        _requests: list = PrivateAttr(default_factory=list)

        async def generate_content_async(self, llm_request, stream=False):
            self._requests.append(llm_request)
            async for response in super().generate_content_async(llm_request, stream):
                yield response

    tasks = FakeTaskStore()
    channels = LocalChannelStore()
    channels.ensure_channel("task-chat")
    llm = CapturingLlm(model="gemini-3.5-flash")
    agent = TaskOrganizerAgent(api_key="offline", llm=llm, clock=_fixed_now)

    async def run():
        return [
            chunk
            async for chunk in agent.chat(
                "Save the attached receipt",
                channels,
                tasks,
                "task-chat",
                attachments=[("image/png", b"\x89PNG-fake-bytes")],
            )
        ]

    asyncio.run(run())

    request = llm._requests[0]
    user_contents = [c for c in request.contents if c.role == "user"]
    parts = user_contents[-1].parts
    assert any(
        part.inline_data and part.inline_data.mime_type == "image/png"
        for part in parts
    )
    assert any(part.text == "Save the attached receipt" for part in parts)


def test_set_task_checkbox_ticks_one_item_in_the_body():
    tasks = FakeTaskStore()
    task = tasks.create_task("Groceries")
    tasks.write_task_body(task.id, "- [ ] Milk\n- [ ] Eggs\nNotes below")
    agent = TaskOrganizerAgent(
        api_key="offline", llm=ScriptedToolLlm(model="gemini-3.5-flash")
    )
    tool = next(t for t in agent.agent.tools if t.__name__ == "set_task_checkbox")

    store_token = agent._store.set(tasks)
    channel_token = agent._channel_id.set("task-chat")
    try:
        ticked = tool(task_id=task.id, item="milk")
        assert ticked == {"changed": True, "item": "Milk", "checked": True}
        assert tasks.get_task_body(task.id) == "- [x] Milk\n- [ ] Eggs\nNotes below"

        unticked = tool(task_id=task.id, item="Milk", checked=False)
        assert unticked["changed"] is True
        assert tasks.get_task_body(task.id) == "- [ ] Milk\n- [ ] Eggs\nNotes below"

        missing = tool(task_id=task.id, item="Bread")
        assert missing["changed"] is False
        assert missing["checkboxes"] == ["Milk", "Eggs"]
    finally:
        agent._channel_id.reset(channel_token)
        agent._store.reset(store_token)


def _task_fields(task):
    return (task.id, task.title, task.status, task.place, task.minutes, task.notes)


def test_a_date_is_only_set_when_one_was_named_and_uses_jerusalem():
    # 23:30 UTC is already the following calendar day in Jerusalem.
    near_midnight_utc = lambda: datetime(
        2026, 1, 1, 23, 30, tzinfo=timezone.utc
    )
    assert infer_when("Remind me to file it", None, near_midnight_utc) is None
    assert infer_when("This is urgent", None, near_midnight_utc) == "2026-01-02"
    assert infer_when("Do it tomorrow", None, near_midnight_utc) == "2026-01-03"

    # A weekly trigger still resolves in Jerusalem, not UTC.
    before_nine = datetime(2026, 8, 23, 17, 59, tzinfo=timezone.utc).timestamp()
    at_nine = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc).timestamp()
    assert next_trigger("daily", before_nine, hour=21) == at_nine
    assert next_trigger("daily", at_nine, hour=21) == at_nine + 86400




def _review_store():
    tasks = FakeTaskStore()
    tasks.create_task("Buy milk and call the plumber")          # two actions
    tasks.create_task("Book the dentist appointment")
    tasks.create_task("Book a dentist appointment")             # near duplicate
    tasks.create_task("Invoices")                               # too vague
    tasks.create_task("Renew the passport", when="2020-01-01")  # long overdue
    return tasks


def test_running_the_organiser_goes_through_the_model_like_any_automation():
    """The review automation has no special path: its prompt reaches the
    model, so the report is written, not assembled from a template."""
    tasks = _review_store()
    channels = LocalChannelStore()
    channels.ensure_channel(ORGANIZE_TASKS.channel_id)
    store = LocalAutomationStore([ORGANIZE_TASKS])

    prompts = []

    class EchoAgent:
        async def chat(self, message, channel_store, task_store, channel_id):
            prompts.append((message, channel_id))
            yield "Two dentist tasks look like duplicates."

    result = asyncio.run(
        AutomationRunner(store, channels, tasks, EchoAgent()).run(ORGANIZE_TASKS.id)
    )

    assert result["model_called"] is True
    assert result["chunks"] == ["Two dentist tasks look like duplicates."]
    assert prompts == [(ORGANIZE_TASKS.prompt, ORGANIZE_TASKS.channel_id)]


def test_avi_can_list_and_run_an_automation_by_name_from_the_chat():
    tasks = _review_store()
    channels = LocalChannelStore()
    channels.ensure_channel(ORGANIZE_TASKS.channel_id)
    agent = TaskOrganizerAgent(
        api_key="offline",
        llm=ScriptedToolLlm(model="gemini-3.5-flash"),
        clock=_fixed_now,
    )
    class EchoAgent:
        async def chat(self, message, channel_store, task_store, channel_id):
            yield "Reviewed the board: possible duplicates found."

    agent.configure_automations(
        AutomationRunner(
            LocalAutomationStore([ORGANIZE_TASKS]), channels, tasks, EchoAgent()
        )
    )
    tools = {tool.__name__: tool for tool in agent.agent.tools}
    token = agent._channel_id.set("task-chat")
    try:
        assert tools["list_automations"]()["automations"] == [
            {
                "name": "Organize tasks",
                "trigger": ORGANIZE_TASKS.schedule,
                "does": ORGANIZE_TASKS.prompt,
            }
        ]

        # A distinctive part of the name is enough, and the report comes back.
        ran = asyncio.run(tools["run_automation"]("organize"))
        assert (ran["ran"], ran["name"]) == (True, "Organize tasks")
        assert "duplicates" in ran["text"].casefold()

        # An unknown name says what exists rather than running the wrong thing.
        missing = asyncio.run(tools["run_automation"]("nope"))
        assert missing["ran"] is False
        assert missing["automations"] == ["Organize tasks"]
    finally:
        agent._channel_id.reset(token)
