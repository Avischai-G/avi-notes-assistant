"""A timed "remind me" writes the task body and fires a ⏰ comment on time."""

from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import chat
from app.task_planning import JERUSALEM


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORONER_KNOWLEDGE_ROOT", str(tmp_path))
    chat.init_chat_stores(use_firestore=False)
    api = FastAPI()
    chat.register_chat_routes(api)
    return TestClient(api)


def _set_reminder(task_id, at):
    agent = chat._agent
    tool = next(t for t in agent.agent.tools if t.__name__ == "set_task_reminder")
    _, task_store, _ = chat.get_stores()
    tokens = [
        (agent._channel_id, agent._channel_id.set("task-chat")),
        (agent._store, agent._store.set(task_store)),
    ]
    try:
        return tool(task_id=task_id, at=at)
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def test_a_timed_reminder_is_written_and_stored(client):
    _, task_store, _ = chat.get_stores()
    task = task_store.create_task("Call the dentist", "Not started")

    result = _set_reminder(task.id, "2030-01-05T10:00")

    assert result == {"reminder_set": "2030-01-05 10:00", "task_id": task.id}
    assert task_store.get_task_body(task.id) == "⏰ Reminder: 2030-01-05 10:00"
    # A dateless task takes the reminder moment as its When.
    assert task_store.list_tasks()[0].when == "2030-01-05T10:00:00"
    [entry] = chat._reminders()
    assert entry["task_id"] == task.id
    assert entry["title"] == "Call the dentist"
    assert entry["at"].startswith("2030-01-05T10:00")


def test_the_tick_fires_due_reminders_and_keeps_future_ones(client):
    _, task_store, _ = chat.get_stores()
    due = task_store.create_task("Water the plants", "Not started")
    later = task_store.create_task("Renew passport", "Not started")

    past = (datetime.now(JERUSALEM) - timedelta(minutes=1)).isoformat()
    future = (datetime.now(JERUSALEM) + timedelta(days=1)).isoformat()
    chat._add_reminder({"task_id": due.id, "at": past, "title": "Water the plants"})
    chat._add_reminder({"task_id": later.id, "at": future, "title": "Renew passport"})

    ticked = client.post("/api/automations/tick").json()

    assert ticked["reminders_fired"] == 1
    [comment] = task_store.list_comments(due.id)
    assert comment["text"] == "⏰ Reminder: Water the plants"
    assert task_store.list_comments(later.id) == []
    [remaining] = chat._reminders()
    assert remaining["task_id"] == later.id


def test_a_reminder_on_a_vanished_task_drops_without_wedging(client):
    past = (datetime.now(JERUSALEM) - timedelta(minutes=1)).isoformat()
    chat._add_reminder({"task_id": "gone", "at": past, "title": "Old thing"})

    ticked = client.post("/api/automations/tick").json()

    assert ticked["reminders_fired"] == 1
    assert chat._reminders() == []


def test_a_bad_time_comes_back_as_a_readable_tool_failure(client):
    _, task_store, _ = chat.get_stores()
    task = task_store.create_task("Vague plan", "Not started")

    result = _set_reminder(task.id, "sometime soon")

    assert "error" in result
    assert task_store.get_task_body(task.id) == ""
    assert chat._reminders() == []


def test_the_device_timezone_is_the_truth_for_naive_times(client):
    agent = chat._agent
    _, task_store, _ = chat.get_stores()
    task = task_store.create_task("Call Tokyo", "Not started")

    tool = next(t for t in agent.agent.tools if t.__name__ == "set_task_reminder")
    from zoneinfo import ZoneInfo

    tokens = [
        (agent._channel_id, agent._channel_id.set("task-chat")),
        (agent._store, agent._store.set(task_store)),
        (agent._tz, agent._tz.set(ZoneInfo("Asia/Tokyo"))),
    ]
    try:
        result = tool(task_id=task.id, at="2030-01-05T10:00")
    finally:
        for var, token in reversed(tokens):
            var.reset(token)

    assert result["reminder_set"] == "2030-01-05 10:00"
    [entry] = chat._reminders()
    # Stored with the device's own offset: 10:00 in Tokyo, not in Jerusalem.
    assert entry["at"] == "2030-01-05T10:00:00+09:00"
