"""Acceptance tests for Avi's defaults and nightly two-plan sweep."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from app.automations import AutomationRunner, LocalAutomationStore, NIGHTLY_PLAN
from app.channel_store import LocalChannelStore
from app.organizer import SYSTEM_PROMPT, TaskOrganizerAgent
from app.task_planning import DayPlanner, infer_when, nightly_due
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


def test_prompt_is_short_and_agent_has_twelve_gated_tools():
    agent = TaskOrganizerAgent(
        api_key="offline",
        llm=ScriptedToolLlm(model="gemini-3.5-flash"),
    )
    assert len(SYSTEM_PROMPT.split()) <= 260
    assert [tool.__name__ for tool in agent.agent.tools] == [
        "create_task",
        "rename_task",
        "move_task",
        "list_tasks",
        "search_tasks",
        "read_task_details",
        "write_task_details",
        "delete_task",
        "restore_task",
        "add_task_comment",
        "read_task_comments",
        "plan_tomorrow",
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

    [task] = tasks.list_tasks()
    assert task.title == "Call the accountant"
    assert task.status == "Not started"
    assert task.when == "2026-08-24"
    assert task.place == "Anywhere"
    assert task.minutes == 30
    assert task.notes == "Remind me to call the accountant"
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


def _task_fields(task):
    return (task.id, task.title, task.status, task.place, task.minutes, task.notes)


def test_silent_sweep_returns_two_different_plans_and_pick_only_sets_when():
    tasks = FakeTaskStore()
    deep = tasks.create_task("Deep proposal", place="Office", minutes=180)
    quick = tasks.create_task("Quick email", place="Anywhere", minutes=15)
    review = tasks.create_task("Review notes", place="Office", minutes=45)
    other = tasks.create_task("Home repair", place="Home", minutes=60)
    done = tasks.create_task("Finished thing", place="Office", minutes=10, lane="Done")
    before = {task.id: _task_fields(task) for task in tasks.list_tasks()}
    channels = LocalChannelStore()
    channels.ensure_channel(NIGHTLY_PLAN.channel_id)
    store = LocalAutomationStore()
    epoch = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc).timestamp()
    planner = DayPlanner(tasks, clock=_fixed_now)
    runner = AutomationRunner(
        store,
        channels,
        tasks,
        object(),
        clock=lambda: epoch,
        planner=planner,
    )

    result = asyncio.run(runner.run(NIGHTLY_PLAN.id))

    assert result["status"] == "ran"
    assert result["model_called"] is False
    assert result["place"] == "Office"
    assert result["text"].startswith("Where will you be tomorrow \u2014")
    assert "I used Office by default." in result["text"]
    assert set(result["plans"]) == {"A", "B"}
    assert [control["label"] for control in result["controls"]] == [
        "Pick Plan A",
        "Pick Plan B",
    ]
    a_ids = [item["task_id"] for item in result["plans"]["A"]]
    b_ids = [item["task_id"] for item in result["plans"]["B"]]
    assert a_ids != b_ids
    assert a_ids == [deep.id, review.id, quick.id]
    assert b_ids == [quick.id, deep.id, review.id]
    assert other.id not in a_ids and done.id not in a_ids
    assert sum(item["minutes"] for item in result["plans"]["A"]) <= 480

    picked = runner.pick_plan("B")

    assert picked["scheduled_task_ids"] == b_ids
    after = {task.id: task for task in tasks.list_tasks()}
    for task_id in b_ids:
        assert after[task_id].when.startswith("2026-08-24T")
        assert _task_fields(after[task_id]) == before[task_id]
    assert after[other.id].when is None
    assert after[done.id].when is None


def test_saying_a_place_in_chat_starts_the_same_two_plan_flow():
    tasks = FakeTaskStore()
    tasks.create_task("Deep proposal", place="Office", minutes=180)
    tasks.create_task("Quick email", place="Anywhere", minutes=15)
    channels = LocalChannelStore()
    channels.ensure_channel("task-chat")
    llm = ScriptedToolLlm(
        model="gemini-3.5-flash",
        tool_name="plan_tomorrow",
        tool_args={"place": "Office"},
    )
    agent = TaskOrganizerAgent(api_key="offline", llm=llm, clock=_fixed_now)
    saved = []
    agent.configure_planning(
        DayPlanner(tasks, clock=_fixed_now), lambda sweep: saved.append(sweep)
    )

    chunks = asyncio.run(
        _turn(agent, "I am at Office tomorrow", channels, tasks)
    )

    assert llm.calls == 2
    assert len(saved) == 1 and saved[0]["place"] == "Office"
    response = next(chunk for chunk in chunks if "text" in chunk)
    assert "Plan A \u2014 heavy first" in response["text"]
    assert "Plan B \u2014 light first" in response["text"]
    assert [control["label"] for control in response["controls"]] == [
        "Pick Plan A",
        "Pick Plan B",
    ]


def test_day_defaults_and_nightly_gate_use_jerusalem_not_utc():
    # 23:30 UTC is already the following calendar day in Jerusalem.
    near_midnight_utc = lambda: datetime(
        2026, 1, 1, 23, 30, tzinfo=timezone.utc
    )
    assert infer_when("Remind me to file it", None, near_midnight_utc) == "2026-01-03"
    assert infer_when("This is urgent", None, near_midnight_utc) == "2026-01-02"

    before_nine = datetime(2026, 8, 23, 17, 59, tzinfo=timezone.utc).timestamp()
    at_nine = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc).timestamp()
    assert nightly_due(before_nine, None) is False
    assert nightly_due(at_nine, None) is True


def test_chat_page_renders_only_the_two_plan_controls_and_wires_pick():
    script = (Path(__file__).parent / "web" / "app.js").read_text()
    assert "controls.length !== 2" in script
    assert "Choose tomorrow's plan" in script
    assert "/api/automations/nightly-plan/pick" in script
    assert "body: JSON.stringify({ plan: control.id })" in script
    assert "customise" not in script.casefold()
