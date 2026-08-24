"""Behavior tests for model-chosen task capture, chat, and day planning."""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from google.adk.models import BaseLlm, LlmResponse
from google.genai import types
from pydantic import Field, PrivateAttr
import pytest

from app.channel_store import LocalChannelStore
from app.organizer import TaskOrganizerAgent
from app.task_planning import DayPlanner
from app.task_store import FakeTaskStore


JERUSALEM = ZoneInfo("Asia/Jerusalem")
NOW = datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM)


class ScriptedLlm(BaseLlm):
    """Choose one tool exactly as a mocked language model would, then answer."""

    tool_name: str | None = None
    tool_args: dict = Field(default_factory=dict)
    tool_sequence: list[tuple[str, dict]] = Field(default_factory=list)
    final_text: str = "Done."
    _calls: list = PrivateAttr(default_factory=list)

    @property
    def calls(self) -> list:
        return self._calls

    async def generate_content_async(self, llm_request, stream=False):
        del stream
        self._calls.append(llm_request)
        sequence_item = self.tool_sequence[len(self._calls) - 1] if len(self._calls) <= len(self.tool_sequence) else None
        selected = sequence_item[0] if sequence_item else self.tool_name
        selected_args = sequence_item[1] if sequence_item else self.tool_args
        if selected and len(self._calls) <= max(1, len(self.tool_sequence)):
            content = types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            name=selected,
                            args=selected_args,
                        )
                    )
                ],
            )
        else:
            content = types.Content(
                role="model", parts=[types.Part(text=self.final_text)]
            )
        yield LlmResponse(content=content, partial=False)


async def _turn(agent, message, channels, store, channel_id):
    return [
        chunk
        async for chunk in agent.chat(
            message,
            channels,
            store,
            channel_id,
        )
    ]


def _exercise(
    message,
    *,
    tool_name=None,
    tool_args=None,
    places=(),
    final_text="Conversation only; nothing was written.",
):
    store = FakeTaskStore()
    for index, place in enumerate(places):
        store.create_task(f"Seed {index}", place=place, minutes=30 + index)
    before = len(store.list_tasks())
    channels = LocalChannelStore()
    channel_id = channels.create_channel()
    model = ScriptedLlm(
        model="gemini-3.5-flash",
        tool_name=tool_name,
        tool_args=tool_args or {},
        final_text=final_text,
    )
    agent = TaskOrganizerAgent(llm=model, clock=lambda: NOW)
    saved = []
    agent.configure_planning(
        DayPlanner(store, clock=lambda: NOW),
        saved.append,
    )
    chunks = asyncio.run(_turn(agent, message, channels, store, channel_id))
    response = next(chunk for chunk in chunks if "text" in chunk)
    return store, before, model, saved, response


TASK_MESSAGES = [
    "remind me to call the dentist tomorrow at 3pm",
    "tomorrow print the contract at the office",
    "remind me to plan the offsite tomorrow",
    "schedule a dentist appointment tomorrow",
    "at the dentist tomorrow",
    "tomorrow I must plan the sprint at the office",
    "email the schedule to Dana tomorrow.",
]


@pytest.mark.parametrize("message", TASK_MESSAGES)
def test_something_to_remember_creates_exactly_one_row(message):
    store, before, model, saved, response = _exercise(
        message,
        tool_name="create_task",
        tool_args={"title": "Captured task"},
    )

    assert before == 0
    assert len(store.list_tasks()) == 1
    assert len([op for op in store.operations if op["action"] == "create"]) == 1
    assert model.calls and saved == []
    assert "Plan A" not in response["text"]
    assert "controls" not in response


PLAN_MESSAGES = [
    ("I will be at Office tomorrow.", "Office"),
    ("I will be at Office tomorrow", "Office"),
    ("I\u0027ll be at Home tomorrow", "Home"),
    ("I\u2019m at Home tomorrow", "Home"),
    ("I am home tomorrow", "Home"),
    ("plan my day tomorrow.", None),
    ("schedule my day", None),
    ("plan tomorrow!", None),
    ("tomorrow I\u0027ll be at the office", "Office"),
]


@pytest.mark.parametrize("message,place", PLAN_MESSAGES)
def test_model_chosen_plan_tool_produces_two_plans_and_no_row(message, place):
    args = {"place": place} if place else {}
    store, before, model, saved, response = _exercise(
        message,
        tool_name="plan_tomorrow",
        tool_args=args,
        places=("Office", "Home", "Anywhere"),
    )

    assert len(store.list_tasks()) == before
    assert len(saved) == 1
    assert len(model.calls) == 2
    assert response["text"] == saved[0]["text"]
    assert "Plan A \u2014 heavy first" in response["text"]
    assert "Plan B \u2014 light first" in response["text"]
    assert [control["label"] for control in response["controls"]] == [
        "Pick Plan A",
        "Pick Plan B",
    ]
    if place:
        assert saved[0]["place"] == place
        assert f"Planning tomorrow for {place}." in response["text"]
        assert "?" not in response["text"]


def test_shot_list_place_statement_names_office_without_a_question():
    _, _, _, saved, response = _exercise(
        "I will be at Office tomorrow.",
        tool_name="plan_tomorrow",
        tool_args={"place": "Office"},
        places=("Office", "Anywhere"),
    )

    assert saved[0]["place"] == "Office"
    assert "Office" in response["text"]
    assert "?" not in response["text"]


@pytest.mark.parametrize("place", ["Studio", "Coffee Shop"])
def test_board_owned_and_multi_word_places_are_used_without_literal_lists(place):
    store, before, _, saved, response = _exercise(
        f"I will be at {place} tomorrow",
        tool_name="plan_tomorrow",
        tool_args={"place": place},
        places=(place,),
    )

    assert DayPlanner(store, clock=lambda: NOW).recent_places() == [place, "Anywhere"]
    assert len(store.list_tasks()) == before
    assert saved[0]["place"] == place
    assert response["text"].startswith(f"Planning tomorrow for {place}.")
    assert "?" not in response["text"]


def test_task_only_reply_is_the_models_own_text():
    _, _, _, saved, response = _exercise(
        "remind me to call the dentist tomorrow",
        tool_name="create_task",
        tool_args={"title": "Call the dentist"},
    )

    assert saved == []
    assert response["text"] == "Conversation only; nothing was written."


def test_plain_chat_reply_passes_through_unmodified():
    store, before, model, saved, response = _exercise(
        "How are you today?",
        final_text="I am well. What are you working on? What is most urgent?",
    )

    assert len(store.list_tasks()) == before == 0
    assert len(model.calls) == 1
    assert saved == []
    assert response["text"] == (
        "I am well. What are you working on? What is most urgent?"
    )
    assert "controls" not in response


def test_empty_plain_chat_reply_uses_done_fallback():
    _, _, _, saved, response = _exercise("Hello", final_text="")

    assert saved == []
    assert response["text"] == "Done."


def test_created_task_remains_visible_when_model_plans_in_same_turn():
    store = FakeTaskStore()
    store.create_task("Office seed", place="Office")
    channels = LocalChannelStore()
    channel_id = channels.create_channel()
    model = ScriptedLlm(
        model="gemini-3.5-flash",
        tool_sequence=[
            ("create_task", {"title": "Buy milk"}),
            ("plan_tomorrow", {"place": "Office"}),
        ],
        final_text="Task written.",
    )
    agent = TaskOrganizerAgent(llm=model, clock=lambda: NOW)
    saved = []
    agent.configure_planning(DayPlanner(store, clock=lambda: NOW), saved.append)

    chunks = asyncio.run(_turn(agent, "buy milk and plan my day at the office", channels, store, channel_id))
    response = next(chunk for chunk in chunks if "text" in chunk)

    assert len(store.list_tasks()) == 2
    assert len(saved) == 1
    assert response["text"] == "Task written.\n\n" + saved[0]["text"]


def test_instruction_shows_current_multi_word_board_place():
    store = FakeTaskStore()
    store.create_task("Studio task", place="Tel Aviv Office")
    agent = TaskOrganizerAgent(llm=ScriptedLlm(model="gemini-3.5-flash"), clock=lambda: NOW)

    instruction = agent.get_instruction(store, query="I will be at the office tomorrow")

    assert "Current Place values on Avi's board: Tel Aviv Office, Anywhere." in instruction


def test_first_turn_in_new_normal_channel_reads_real_board_places():
    class MissingChannelReturnsNone(LocalChannelStore):
        def get_channel(self, channel_id):
            return self.channels.get(channel_id)

    class FirstTurnOrganizer(TaskOrganizerAgent):
        @staticmethod
        def _last_question(messages):
            return TaskOrganizerAgent._last_question(messages or [])

    store = FakeTaskStore()
    store.create_task("Studio task", place="Tel Aviv Office")
    channels = MissingChannelReturnsNone()
    model = ScriptedLlm(model="gemini-3.5-flash", final_text="Hello.")
    agent = FirstTurnOrganizer(llm=model, clock=lambda: NOW)

    asyncio.run(_turn(agent, "Hello", channels, store, "fresh-normal-chat"))

    instruction = model.calls[0].config.system_instruction
    assert "Current Place values on Avi's board: Tel Aviv Office, Anywhere." in instruction


def test_automation_turn_neither_reads_nor_claims_board_places():
    class BoardReadForbidden(FakeTaskStore):
        def list_tasks(self, lane=None):
            raise AssertionError("automation instruction must not read the board")

    store = BoardReadForbidden()
    channels = LocalChannelStore()
    model = ScriptedLlm(model="gemini-3.5-flash", final_text="Cleanup complete.")
    agent = TaskOrganizerAgent(llm=model, clock=lambda: NOW)

    asyncio.run(
        _turn(
            agent,
            "Clean up knowledge.",
            channels,
            store,
            "automation-knowledge-cleanup",
        )
    )

    instruction = model.calls[0].config.system_instruction
    assert "Current Place values on Avi's board:" not in instruction
