"""The two things Settings can change: the chat prompt, and each automation."""
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import chat
from app.automations import next_run_from_schedule
from app.organizer import SYSTEM_PROMPT
from app.task_planning import JERUSALEM


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


def test_automations_expose_and_accept_a_prompt_and_a_trigger(client):
    listed = client.get("/api/automations").json()["automations"]
    assert [a["id"] for a in listed] == ["knowledge-cleanup", "nightly-plan"]
    assert all(a["built_in"] for a in listed)
    assert listed[1]["prompt"] == "Plan tomorrow from Avi's open tasks."

    created = client.post(
        "/api/automations",
        json={"name": "Morning brief", "prompt": "Summarise today.", "schedule": "daily at 07:30"},
    ).json()
    assert created["id"] == "morning-brief"
    assert created["channel_id"] == "automation-morning-brief"
    assert created["built_in"] is False

    patched = client.patch(
        "/api/automations/morning-brief", json={"schedule": "  daily at 06:15  "}
    ).json()
    assert patched["schedule"] == "daily at 06:15"
    assert client.get("/api/automations").json()["automations"][-1]["schedule"] == "daily at 06:15"

    # A second automation of the same name gets its own id, not a collision.
    assert client.post("/api/automations", json={"name": "Morning brief"}).json()["id"] == "morning-brief-2"

    assert client.delete("/api/automations/morning-brief").status_code == 200
    assert client.delete("/api/automations/morning-brief").status_code == 404
    # The planning path looks the built-ins up by id, so they stay.
    assert client.delete("/api/automations/nightly-plan").status_code == 409
    assert client.patch("/api/automations/nope", json={}).status_code == 404


def test_an_explicit_time_in_the_trigger_becomes_the_next_run():
    now = datetime(2026, 8, 24, 9, 0, tzinfo=JERUSALEM).timestamp()

    plain = next_run_from_schedule("daily", now)
    assert plain == now + 86400

    timed = datetime.fromtimestamp(next_run_from_schedule("daily at 07:30", now), JERUSALEM)
    assert (timed.date().day, timed.hour, timed.minute) == (25, 7, 30)  # 07:30 already passed

    later = datetime.fromtimestamp(next_run_from_schedule("every day at 21:00", now), JERUSALEM)
    assert (later.date().day, later.hour, later.minute) == (24, 21, 0)

    # A number that is not a time of day leaves the plain daily cadence alone.
    assert next_run_from_schedule("run 99:99 times", now) == now + 86400
