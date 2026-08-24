"""Test routing logic: reminder creation vs day planning."""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from google.adk.models import BaseLlm, LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from app.organizer import TaskOrganizerAgent
from app.channel_store import LocalChannelStore
from app.task_store import FakeTaskStore
from app.task_planning import DayPlanner


JERUSALEM = ZoneInfo("Asia/Jerusalem")


class RecordingLlm(BaseLlm):
    """LLM that records calls and returns neutral text."""
    _calls: list = PrivateAttr(default_factory=list)

    @property
    def calls(self):
        return self._calls

    async def generate_content_async(self, llm_request, stream=False):
        del stream
        self._calls.append(llm_request)
        # Return neutral text that doesn't trigger any tool calls
        yield LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text="Understood.")]
            )
        )


def test_1_reminder_with_unknown_time_does_not_trigger_plan():
    """Routing test: 'remind me tomorrow at 3pm' should NOT trigger planner."""
    channels = LocalChannelStore()
    channel_id = channels.create_channel()
    model = RecordingLlm(model="gemini-3.5-flash")
    agent = TaskOrganizerAgent(
        llm=model, clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM)
    )

    async def run():
        chunks = []
        async for chunk in agent.chat(
            user_message="remind me to call the dentist tomorrow at 3pm",
            channel_store=channels,
            task_store=FakeTaskStore(),
            channel_id=channel_id,
        ):
            chunks.append(chunk)
        return chunks

    result = asyncio.run(run())
    # Should route to task creation path (not planner path)
    text = "".join(c.get("text", "") for c in result)
    assert "Planning tomorrow for" not in text, "Should not trigger planner for reminders"


def test_2_reminder_with_office_location_does_not_trigger_plan():
    """Routing test: 'remind me at the office tomorrow' should NOT trigger planner."""
    channels = LocalChannelStore()
    channel_id = channels.create_channel()
    model = RecordingLlm(model="gemini-3.5-flash")
    agent = TaskOrganizerAgent(
        llm=model, clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM)
    )

    async def run():
        chunks = []
        async for chunk in agent.chat(
            user_message="remind me when I'm at the office tomorrow",
            channel_store=channels,
            task_store=FakeTaskStore(),
            channel_id=channel_id,
        ):
            chunks.append(chunk)
        return chunks

    result = asyncio.run(run())
    text = "".join(c.get("text", "") for c in result)
    assert "Planning tomorrow for" not in text, "Should not trigger planner for reminders even with place"


def test_3_plan_request_triggers_planner():
    """Routing test: 'plan my day tomorrow' SHOULD trigger planner."""
    store = FakeTaskStore()
    channels = LocalChannelStore()
    channel_id = channels.create_channel()
    model = RecordingLlm(model="gemini-3.5-flash")
    agent = TaskOrganizerAgent(
        llm=model, clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM)
    )
    planner = DayPlanner(store, clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM))
    agent.configure_planning(planner, lambda sweep: None)

    async def run():
        chunks = []
        async for chunk in agent.chat(
            user_message="plan my day tomorrow",
            channel_store=channels,
            task_store=store,
            channel_id=channel_id,
        ):
            chunks.append(chunk)
        return chunks

    result = asyncio.run(run())
    text = "".join(c.get("text", "") for c in result)
    # Should trigger planner and use default place
    assert "Plan A" in text and "Plan B" in text, "Should trigger planner for plan requests"
    assert "Anywhere" in text, "Should use default place on empty board"
    # Model should not be called since planning is deterministic
    assert len(model.calls) == 0, "Plan route should not call LLM"


def test_4_plan_request_with_place_triggers_planner():
    """Routing test: 'plan my day tomorrow at the office' SHOULD trigger planner."""
    store = FakeTaskStore()
    channels = LocalChannelStore()
    channel_id = channels.create_channel()
    model = RecordingLlm(model="gemini-3.5-flash")
    agent = TaskOrganizerAgent(
        llm=model, clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM)
    )
    planner = DayPlanner(store, clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM))
    agent.configure_planning(planner, lambda sweep: None)

    async def run():
        chunks = []
        async for chunk in agent.chat(
            user_message="plan my day tomorrow at the office",
            channel_store=channels,
            task_store=store,
            channel_id=channel_id,
        ):
            chunks.append(chunk)
        return chunks

    result = asyncio.run(run())
    text = "".join(c.get("text", "") for c in result)
    # Should trigger planner and extract Office as place
    assert "Planning tomorrow for Office" in text, "Should trigger planner and mention Office"
    assert "Plan A" in text and "Plan B" in text, "Should show two plans"
    assert len(model.calls) == 0, "Plan route should not call LLM"


def test_5_plan_verb_variations_trigger_planner():
    """Routing test: Plan requests with various phrasings all trigger planner."""
    plan_requests = [
        "schedule my day tomorrow",
        "plan tomorrow",
        "help me plan my day",
        "schedule tomorrow at home",
    ]

    for phrase in plan_requests:
        store = FakeTaskStore()
        channels = LocalChannelStore()
        channel_id = channels.create_channel()
        model = RecordingLlm(model="gemini-3.5-flash")
        agent = TaskOrganizerAgent(
            llm=model, clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM)
        )
        planner = DayPlanner(store, clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM))
        agent.configure_planning(planner, lambda sweep: None)

        async def run():
            chunks = []
            async for chunk in agent.chat(
                user_message=phrase,
                channel_store=channels,
                task_store=store,
                channel_id=channel_id,
            ):
                chunks.append(chunk)
            return chunks

        result = asyncio.run(run())
        text = "".join(c.get("text", "") for c in result)
        assert (
            "Plan A" in text and "Plan B" in text
        ), f"'{phrase}' should trigger planner (route to day planning)"


def test_6_reminder_verb_variations_do_not_trigger_planner():
    """Routing test: Reminder requests should route to task creation, not planning."""
    reminders = [
        "remind me to call the dentist tomorrow at 3pm",
        "remind me to call the plumber",
        "call mom when you remember",
        "buy milk on the way home",
        "pay the electricity bill tomorrow",
        "book a flight for next month",
        "remember to take vitamins with breakfast",
        "send birthday gift to Sarah",
        "pick up dry cleaning",
        "water the plants tonight",
        "follow up on the contract email",
        "schedule a doctor appointment",
    ]

    for reminder in reminders:
        store = FakeTaskStore()
        channels = LocalChannelStore()
        channel_id = channels.create_channel()
        model = RecordingLlm(model="gemini-3.5-flash")
        agent = TaskOrganizerAgent(
            llm=model, clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM)
        )

        async def run():
            chunks = []
            async for chunk in agent.chat(
                user_message=reminder,
                channel_store=channels,
                task_store=store,
                channel_id=channel_id,
            ):
                chunks.append(chunk)
            return chunks

        result = asyncio.run(run())
        text = "".join(c.get("text", "") for c in result)
        # Should NOT trigger planner (route to task creation)
        assert (
            "Planning tomorrow for" not in text
        ), f"'{reminder}' should NOT trigger planner (route to task creation)"
