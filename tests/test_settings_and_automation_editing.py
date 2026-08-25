"""What the ⋯ menus can change: the chat prompt, and each automation's trigger."""
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import chat
from app.automations import Automation, LocalAutomationStore, reconcile_triggers
from app.organizer import SYSTEM_PROMPT
from app.task_planning import JERUSALEM, describe_trigger, next_trigger


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORONER_KNOWLEDGE_ROOT", str(tmp_path))
    chat.init_chat_stores(use_firestore=False)
    api = FastAPI()
    chat.register_chat_routes(api)
    return TestClient(api)


def test_system_prompt_round_trips_and_reaches_the_agent(client):
    assert client.get("/api/settings").json()["system_prompt"] == SYSTEM_PROMPT

    saved = client.put("/api/settings", json={"system_prompt": "  Be terse.  "})
    assert saved.status_code == 200
    assert saved.json()["system_prompt"] == "Be terse."
    assert client.get("/api/settings").json()["system_prompt"] == "Be terse."

    _, task_store, agent = chat.get_stores()
    assert agent.get_instruction(task_store).startswith("Be terse.")

    assert client.put("/api/settings", json={"system_prompt": "   "}).status_code == 400


def test_the_board_ships_with_one_automation_and_retires_knowledge_cleanup(client):
    listed = client.get("/api/automations").json()["automations"]
    assert [a["id"] for a in listed] == ["nightly-plan"]
    assert listed[0]["built_in"] is True
    assert (listed[0]["frequency"], listed[0]["hour"]) == ("daily", 21)
    assert listed[0]["schedule"] == "Daily at 21:00"
    assert client.get("/api/channels/automation-knowledge-cleanup").json()["total"] == 0


def test_an_automation_carries_a_frequency_and_a_when(client):
    created = client.post(
        "/api/automations",
        json={"name": "Morning brief", "prompt": "Summarise today.",
              "frequency": "daily", "hour": 7, "minute": 30},
    ).json()
    assert created["id"] == "morning-brief"
    assert created["channel_id"] == "automation-morning-brief"
    assert created["built_in"] is False
    assert created["schedule"] == "Daily at 07:30"

    weekly = client.patch(
        "/api/automations/morning-brief",
        json={"frequency": "weekly", "weekday": 2, "hour": 18, "minute": 15},
    ).json()
    assert weekly["schedule"] == "Weekly on Wednesday at 18:15"

    hourly = client.patch(
        "/api/automations/morning-brief", json={"frequency": "hourly", "minute": 5}
    ).json()
    assert hourly["schedule"] == "Hourly at :05"

    # A second automation of the same name gets its own id, not a collision.
    assert client.post("/api/automations", json={"name": "Morning brief"}).json()["id"] == "morning-brief-2"

    assert client.delete("/api/automations/morning-brief").status_code == 200
    assert client.delete("/api/automations/morning-brief").status_code == 404
    # The planning path looks the built-in up by id, so it stays.
    assert client.delete("/api/automations/nightly-plan").status_code == 409
    assert client.patch("/api/automations/nope", json={}).status_code == 404


def test_a_bad_trigger_is_refused_rather_than_stored(client):
    client.post("/api/automations", json={"name": "Probe"})
    for bad in ({"frequency": "yearly"}, {"hour": 24}, {"minute": -1},
                {"weekday": 7}, {"hour": "nine"}):
        assert client.patch("/api/automations/probe", json=bad).status_code == 400, bad
    assert client.get("/api/automations").json()["automations"][-1]["schedule"] == "Daily at 09:00"


def test_a_pre_trigger_record_is_repaired_rather_than_silently_retimed():
    """The live nightly plan predated structured triggers.

    Its stored document carried `daily at 21:00 Asia/Jerusalem` as text with no
    frequency fields, so the dataclass defaults made it 09:00 — the automation
    would have quietly moved twelve hours.
    """
    stale = Automation(
        id="nightly-plan",
        name="Plan tomorrow",
        prompt="Plan tomorrow from Avi's open tasks.",
        schedule="daily at 21:00 Asia/Jerusalem",
        enabled=True,
        channel_id="automation-nightly-plan",
    )
    assert (stale.frequency, stale.hour) == ("daily", 9)  # the wrong fallback

    mine = Automation(
        id="mine", name="Mine", prompt="", schedule="Hourly at :10", enabled=True,
        channel_id="automation-mine", frequency="hourly", minute=10,
    )
    store = LocalAutomationStore([stale, mine])
    now = datetime(2026, 8, 25, 9, 0, tzinfo=JERUSALEM).timestamp()

    repaired = reconcile_triggers(store, now)

    assert [a.id for a in repaired] == ["nightly-plan"]  # `mine` already agrees
    fixed = store.get("nightly-plan")
    assert (fixed.frequency, fixed.hour, fixed.minute) == ("daily", 21, 0)
    assert fixed.schedule == "Daily at 21:00"
    assert fixed.next_run_at == datetime(2026, 8, 25, 21, 0, tzinfo=JERUSALEM).timestamp()
    # Idempotent: a second boot changes nothing.
    assert reconcile_triggers(store, now) == []


def test_next_trigger_lands_on_the_next_matching_moment():
    # Monday 2026-08-24, 09:00 Jerusalem.
    now = datetime(2026, 8, 24, 9, 0, tzinfo=JERUSALEM)
    at = lambda *args, **kwargs: datetime.fromtimestamp(
        next_trigger(*args, **kwargs), JERUSALEM
    )

    assert at("hourly", now.timestamp(), minute=30) == now.replace(minute=30)
    # :00 has already passed this hour, so it rolls to the next one.
    assert at("hourly", now.timestamp(), minute=0) == now.replace(hour=10)

    assert at("daily", now.timestamp(), hour=21) == now.replace(hour=21)
    assert at("daily", now.timestamp(), hour=7) == now.replace(day=25, hour=7)

    # Monday 18:00 is still ahead; Monday 07:00 has passed, so it waits a week.
    assert at("weekly", now.timestamp(), hour=18, weekday=0) == now.replace(hour=18)
    assert at("weekly", now.timestamp(), hour=7, weekday=0) == now.replace(day=31, hour=7)
    assert at("weekly", now.timestamp(), hour=7, weekday=4) == now.replace(day=28, hour=7)


def test_describe_trigger_is_the_one_sentence_the_ui_shows():
    assert describe_trigger("hourly", 9, 5, 0) == "Hourly at :05"
    assert describe_trigger("daily", 21, 0, 0) == "Daily at 21:00"
    assert describe_trigger("weekly", 8, 45, 6) == "Weekly on Sunday at 08:45"
