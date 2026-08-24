"""Regression tests for routing fixes.

Tests for:
1. Trailing punctuation in place statements
2. Tasks containing 'plan' or 'schedule' alongside 'day' or 'tomorrow'
"""
import pytest
from app.organizer import TaskOrganizerAgent as A


def test_place_statements_with_trailing_punctuation():
    """Test that trailing punctuation does not break place statement matching."""
    # These should all be recognized as place statements (routing to plans)
    # Apostrophes as unicode escapes to prevent editor substitution
    place_with_punctuation = [
        "I will be at Office tomorrow.",
        "I am at Office tomorrow.",
        "I’ll be at the Office tomorrow.",  # U+2019 curly apostrophe
        "I’ll be home tomorrow.",  # U+2019 curly apostrophe
        "Office.",
        "tomorrow at office.",
    ]
    for msg in place_with_punctuation:
        assert A._is_bare_place_statement(msg), f"Failed for: {msg!r}"


def test_task_messages_not_hijacked_by_plan_words():
    """Test that tasks containing 'plan'/'schedule' + 'day'/'tomorrow' still create rows."""
    # These should NOT be recognized as plan requests (should create rows)
    tasks_with_plan_words = [
        "remind me to plan the offsite tomorrow",
        "schedule a dentist appointment tomorrow",
        "remind me to schedule the standup tomorrow",
        "plan the birthday party tomorrow",
        "remind me to plan meals for the day",
        "I need to schedule the car service tomorrow",
        "remind me to review the plan tomorrow",
        "tomorrow: finish the schedule for the team",
    ]
    for msg in tasks_with_plan_words:
        assert not A._is_asking_for_plan(msg), f"Wrongly hijacked task: {msg!r}"
        assert not A._is_bare_place_statement(msg), f"Wrongly routed as place: {msg!r}"
