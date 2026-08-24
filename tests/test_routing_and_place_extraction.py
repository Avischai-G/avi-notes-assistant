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
    final_text: str = "Done."
    _calls: list = PrivateAttr(default_factory=list)

    @property
    def calls(self) -> list:
        return self._calls

    async def generate_content_async(self, llm_request, stream=False):
        del stream
        self._calls.append(llm_request)
        if self.tool_name and len(self._calls) == 1:
            content = types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            name=self.tool_name,
                            args=self.tool_args,
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


def _exercise(message, *, tool_name=None, tool_args=None, places=()):
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
        final_text="Conversation only; nothing was written.",
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


def test_plain_question_creates_no_row_and_no_plan():
    store, before, model, saved, response = _exercise("How are you today?")

    assert len(store.list_tasks()) == before == 0
    assert len(model.calls) == 1
    assert saved == []
    assert "Plan A" not in response["text"]
    assert "controls" not in response
