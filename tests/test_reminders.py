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
    # The fake board has a Reminder column, so the property is the home
    # and the page body stays clean.
    assert task_store.reminders[task.id].startswith("2030-01-05T10:00")
    assert task_store.get_task_body(task.id) == ""
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


def test_a_board_without_a_reminder_column_falls_back_to_the_body(client, monkeypatch):
    _, task_store, _ = chat.get_stores()
    task = task_store.create_task("Old board", "Not started")
    monkeypatch.setattr(task_store, "has_column", lambda name: name != "Reminder")

    result = _set_reminder(task.id, "2030-01-05T10:00")

    assert result["reminder_set"] == "2030-01-05 10:00"
    assert task.id not in task_store.reminders
    assert task_store.get_task_body(task.id) == "⏰ Reminder: 2030-01-05 10:00"


def test_a_fired_reminder_clears_its_column_and_pushes(client, monkeypatch):
    _, task_store, _ = chat.get_stores()
    task = task_store.create_task("Water the flowers", "Not started")
    pushed = []
    monkeypatch.setattr(chat, "_push_to_devices", lambda title, body: pushed.append(title))

    past = (datetime.now(JERUSALEM) - timedelta(minutes=1)).isoformat()
    chat._add_reminder({"task_id": task.id, "at": past, "title": "Water the flowers"})
    task_store.set_reminder(task.id, past)

    ticked = client.post("/api/automations/tick").json()

    assert ticked["reminders_fired"] == 1
    assert task.id not in task_store.reminders  # the column shows only pending
    assert pushed == ["⏰ Water the flowers"]
    [comment] = task_store.list_comments(task.id)
    assert comment["text"] == "⏰ Reminder: Water the flowers"


def test_the_notify_tool_pushes_now_and_admits_having_no_devices(client, monkeypatch):
    agent = chat._agent
    assert agent.notification_sink is chat._push_to_devices
    tool = next(t for t in agent.agent.tools if t.__name__ == "notify")
    token = agent._channel_id.set("task-chat")
    try:
        # No device enrolled: the tool says so instead of pretending.
        empty = tool(message="Drink water")
        assert empty["notified"] is False
        assert "Settings" in empty["reason"]

        pushed = []
        monkeypatch.setattr(
            agent, "notification_sink", lambda title, body: (pushed.append(title), 2)[1]
        )
        result = tool(message="Drink water")
    finally:
        agent._channel_id.reset(token)

    assert result == {"notified": True, "devices": 2}
    assert pushed == ["🔔 Drink water"]


def test_a_long_notify_message_travels_in_the_expandable_body(client, monkeypatch):
    # Android truncates the title and never expands it; the full text must
    # ride in the body, which does unfold.
    agent = chat._agent
    tool = next(t for t in agent.agent.tools if t.__name__ == "notify")
    sent = {}

    def capture(title, body):
        sent["title"], sent["body"] = title, body
        return 1

    monkeypatch.setattr(agent, "notification_sink", capture)
    message = "Overdue tasks: Buy international driving permit and renew the passport"
    token = agent._channel_id.set("task-chat")
    try:
        assert tool(message=message)["notified"] is True
    finally:
        agent._channel_id.reset(token)

    assert sent["title"].startswith("🔔 ")
    assert sent["title"].endswith("…")
    assert len(sent["title"]) <= 45
    assert sent["body"] == message


def test_the_stored_pem_reaches_pywebpush_as_a_loaded_vapid_key(client, monkeypatch):
    # pywebpush reads a str key as a file path or raw base64 — handing it the
    # stored PEM text fails before any network call, silently killing every
    # push. The PEM must arrive pre-loaded as a Vapid instance.
    import pywebpush
    from py_vapid import Vapid01

    client.post("/api/push/subscribe", json={
        "endpoint": "https://push.example/abc",
        "keys": {"p256dh": "pk", "auth": "au"},
    })
    captured = {}

    def fake_webpush(subscription_info, data, vapid_private_key, vapid_claims):
        captured["key"] = vapid_private_key

    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)
    assert chat._push_to_devices("⏰ Test", "due") == 1
    assert isinstance(captured["key"], Vapid01)


def test_push_subscriptions_register_and_validate(client):
    assert "key" in client.get("/api/push/key").json()

    good = client.post("/api/push/subscribe", json={
        "endpoint": "https://push.example/abc",
        "keys": {"p256dh": "pk", "auth": "au"},
    })
    assert good.json()["subscribed"] is True
    [stored] = chat._push_subscriptions()
    assert stored["endpoint"] == "https://push.example/abc"

    assert client.post("/api/push/subscribe", json={"endpoint": "nope"}).status_code == 400
    assert client.post(
        "/api/push/subscribe", json={"endpoint": "https://x", "keys": {}}
    ).status_code == 400

    # Turning a device off forgets exactly that endpoint.
    off = client.post(
        "/api/push/unsubscribe", json={"endpoint": "https://push.example/abc"}
    )
    assert off.json() == {"subscribed": False, "devices": 0}
    assert chat._push_subscriptions() == []
    assert client.post("/api/push/unsubscribe", json={}).status_code == 400
