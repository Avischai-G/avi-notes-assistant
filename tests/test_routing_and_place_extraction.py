"""Test routing: task creation vs day planning via table-driven cases."""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from google.adk.models import BaseLlm, LlmResponse
from google.genai import types
from pydantic import PrivateAttr
import pytest

from app.organizer import TaskOrganizerAgent
from app.channel_store import LocalChannelStore
from app.task_store import FakeTaskStore
from app.task_planning import DayPlanner


JERUSALEM = ZoneInfo("Asia/Jerusalem")


class CapturingLlm(BaseLlm):
    """LLM that captures calls and returns neutral text."""
    _calls: list = PrivateAttr(default_factory=list)

    @property
    def calls(self):
        return self._calls

    async def generate_content_async(self, llm_request, stream=False):
        del stream
        self._calls.append(llm_request)
        yield LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text="Noted.")]
            )
        )


async def route_message(message, agent, channels, store, channel_id):
    """Send a message through the organizer and return response text."""
    chunks = []
    async for chunk in agent.chat(
        user_message=message,
        channel_store=channels,
        task_store=store,
        channel_id=channel_id,
    ):
        chunks.append(chunk)
    return "".join(c.get("text", "") for c in chunks)


# Table of all test cases: (message, expected_route, description)
TEST_CASES = [
    # Cases that should route to PLANS (explicit request or bare place statement)
    ("I am at Office tomorrow", "plans", "bare place with preposition"),
    ("I will be at the Office tomorrow", "plans", "I will be with preposition"),
    ("tomorrow at Office", "plans", "leading tomorrow at place"),
    ("Office", "plans", "place name only"),
    ("plan my day tomorrow", "plans", "explicit plan request"),
    ("plan my day tomorrow at the office", "plans", "plan request with place"),
    ("schedule tomorrow", "plans", "explicit schedule request"),
    ("schedule my day at home", "plans", "schedule with place"),

    # Cases that should route to TASK CREATION (from probed 22 phrasings)
    ("remind me to call the dentist tomorrow at 3pm", "row", "reminder with time"),
    ("remind me to call the plumber when I'm at the office tomorrow", "row", "reminder with place"),
    ("tomorrow I need to fix the sink at home", "row", "task with embedded place"),
    ("tomorrow, grab milk at the office", "row", "task verb with embedded place"),
    ("finish the report at the office tomorrow", "row", "finish verb"),
    ("drop off the keys at home tomorrow", "row", "drop off verb"),
    ("tomorrow print the contract at the office", "row", "print verb"),
    ("take the car in tomorrow at the garage", "row", "take verb"),
    ("collect the parcel at the office tomorrow", "row", "collect verb"),
    ("tomorrow check the mail at home", "row", "check verb"),
    ("tomorrow I have the dentist at 9 near the office", "row", "appointment with time"),
    ("water the plants at home tomorrow", "row", "water verb"),
    ("tomorrow settle the invoice at the office", "row", "settle verb"),
    ("sign the lease at home tomorrow morning", "row", "sign verb"),
    ("pay the electricity bill tomorrow", "row", "pay verb"),
    ("book a flight for next month", "row", "book verb"),
    ("pick up dry cleaning", "row", "pick up verb"),
    ("send birthday gift to Sarah", "row", "send verb"),
    ("follow up on the contract email", "row", "follow up verb"),
    ("return the book at the library tomorrow", "row", "return verb"),
    ("repair the fence at the backyard tomorrow", "row", "repair verb"),
    ("organize the closet at home tomorrow", "row", "organize verb"),
]


@pytest.mark.parametrize("message,expected_route,description", TEST_CASES)
def test_routing_comprehensive(message, expected_route, description):
    """Table-driven routing test: all cases must route correctly."""
    store = FakeTaskStore()
    channels = LocalChannelStore()
    channel_id = channels.create_channel()
    model = CapturingLlm(model="gemini-3.5-flash")
    agent = TaskOrganizerAgent(
        llm=model, clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM)
    )
    planner = DayPlanner(store, clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM))
    agent.configure_planning(planner, lambda sweep: None)

    result = asyncio.run(route_message(message, agent, channels, store, channel_id))

    if expected_route == "plans":
        # Should show plan output (Plan A and Plan B)
        assert (
            "Plan A" in result and "Plan B" in result
        ), f"'{message}' ({description}) should route to plans, got: {result[:100]}"
        # Should NOT call the model
        assert len(model.calls) == 0, f"Plans should not call model"
    else:  # expected_route == "row"
        # Should NOT show plan output
        assert (
            "Plan A" not in result or "Plan B" not in result
        ), f"'{message}' ({description}) should NOT route to plans, got: {result[:100]}"
        # SHOULD call the model (to create the task)
        assert len(model.calls) >= 1, f"'{message}' should route to task creation (call model)"
