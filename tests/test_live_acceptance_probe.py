from __future__ import annotations

import pytest

from tools.live_acceptance_probe import _assert_only_when_changed, _plan_entries


def _row(task_id: str, *, when: str, title: str = "Synthetic task") -> dict:
    return {
        "id": task_id,
        "title": title,
        "status": "Not started",
        "when": when,
        "place": "Anywhere",
        "minutes": 30,
        "notes": "Synthetic acceptance marker",
    }


def test_live_probe_parses_two_differently_ordered_plans():
    text = """Planning tomorrow for Office.

Plan A — heavy first
09:00 · Long task · 180 min
12:00 · Quick task · 15 min

Plan B — light first
09:00 · Quick task · 15 min
09:15 · Long task · 180 min"""

    plans = _plan_entries(text)

    assert [entry["title"] for entry in plans["A"]] == ["Long task", "Quick task"]
    assert [entry["title"] for entry in plans["B"]] == ["Quick task", "Long task"]


def test_live_probe_accepts_when_only_change():
    before = [_row("one", when="2026-08-24"), _row("two", when="2026-08-24")]
    after = [
        _row("one", when="2026-08-24T09:00:00+03:00"),
        _row("two", when="2026-08-24T09:30:00+03:00"),
    ]

    _assert_only_when_changed(before, after)


def test_live_probe_rejects_non_when_change():
    before = [_row("one", when="2026-08-24")]
    after = [_row("one", when="2026-08-24T09:00:00+03:00", title="Changed")]

    with pytest.raises(AssertionError, match="changed title"):
        _assert_only_when_changed(before, after)
