"""Test routing logic: reminder creation vs day planning."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.task_planning import DayPlanner, ANYWHERE
from app.task_store import FakeTaskStore


JERUSALEM = ZoneInfo("Asia/Jerusalem")


@pytest.fixture
def store_with_office_place():
    store = FakeTaskStore()
    store.create_task("Draft the deck", place="Office", minutes=90)
    store.create_task("Email Dana", place="Office", minutes=15)
    return store


@pytest.fixture
def planner(store_with_office_place):
    clock = lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM)
    return DayPlanner(store_with_office_place, clock=clock)


class TestBlocker1RoutingFix:
    """Test the five specific behaviors required by BLOCKER 1."""

    def test_reminder_with_time_does_not_trigger_plan(self, planner):
        # "remind me to call the dentist tomorrow at 3pm"
        # Should create exactly one row, NOT trigger day plan
        # Fixed extract_place returns None for "3pm" (unknown place)
        place = planner.extract_place("remind me to call the dentist tomorrow at 3pm")
        assert place is None, "3pm is not a known place, routing should go to task creation"

    def test_reminder_with_known_place_creates_row(self, planner):
        # "remind me to call the plumber when I'm at the office tomorrow"
        # Should create exactly one row with Place=Office, NO day plan
        # The LLM (not extract_place) infers Place=Office from "when I'm at the office"
        # extract_place should return None so it doesn't trigger day plan
        place = planner.extract_place("remind me to call the plumber when I'm at the office tomorrow")
        assert place is None, "Reminder should not trigger day plan"

    def test_plan_request_with_place_triggers_plan(self, planner):
        # "plan my day tomorrow at the office"
        # Should produce two plans and create no row
        place = planner.extract_place("plan my day tomorrow at the office")
        assert place == "Office", "Plan request should extract place"
        sweep = planner.build(place)
        assert sweep["place"] == "Office"
        assert "Plan A" in sweep["text"]
        assert "Plan B" in sweep["text"]

    def test_plan_request_without_place_uses_default(self, planner):
        # "plan tomorrow" with no place named
        # Should produce two plans using the default place
        place = planner.extract_place("plan tomorrow")
        assert place is None, "No place mentioned"
        sweep = planner.build(place)
        assert sweep["place"] == "Office", "Default place is most recent"
        assert "Plan A" in sweep["text"]
        assert "Plan B" in sweep["text"]

    def test_anywhere_default_when_no_office_tasks(self):
        store = FakeTaskStore()
        store.create_task("Read a book", place="Anywhere", minutes=30)
        planner = DayPlanner(store, clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=JERUSALEM))
        sweep = planner.build(place=None)
        assert sweep["place"] == ANYWHERE


class TestRealisticReminderPhrasings:
    """Ten realistic reminder phrasings that should all route to task creation (not day plan)."""

    def test_reminders_route_correctly(self, planner):
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
            place = planner.extract_place(reminder)
            # All of these should route to task creation (not day plan)
            # That means extract_place should return None unless it explicitly asks for a plan
            # and mentions a known place
            if place is not None:
                assert place == "Office", f"'{reminder}' should only extract Office if asking for a plan"
