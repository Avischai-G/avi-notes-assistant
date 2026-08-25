"""With CORONER_REQUIRE_DEVICE_KEY, no browser request rides server credentials."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import chat


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORONER_KNOWLEDGE_ROOT", str(tmp_path))
    chat.init_chat_stores(use_firestore=False)
    api = FastAPI()
    chat.register_chat_routes(api)
    monkeypatch.setattr(chat, "_REQUIRE_DEVICE_KEY", True)
    return TestClient(api)


def test_chat_refuses_without_a_device_key(client):
    response = client.post("/api/channels/home/chat", json={"message": "hi"})
    assert response.status_code == 401
    assert "Settings" in response.json()["detail"]


def test_manual_automation_run_refuses_without_a_device_key(client):
    response = client.post("/api/automations/organize-tasks/run")
    assert response.status_code == 401


def test_settings_announce_the_requirement(client):
    assert client.get("/api/settings").json()["require_key"] is True


def test_key_check_requires_the_header(client):
    assert client.post("/api/key-check").status_code == 400


KEY = "k" * 30


def test_key_check_refuses_an_ineligible_model_before_any_network(client):
    result = client.post(
        "/api/key-check",
        headers={"X-Gemini-Key": KEY, "X-Gemini-Model": "gpt-4o"},
    ).json()
    assert result["ok"] is False
    assert "Gemini 3.5" in result["reason"]


def test_a_malformed_model_identifier_is_a_client_error(client):
    response = client.post(
        "/api/key-check",
        headers={"X-Gemini-Key": KEY, "X-Gemini-Model": "not a model!!"},
    )
    assert response.status_code == 400


def test_deleting_a_chat_is_gated_and_really_empties_it(client):
    from app.channel_store import Message

    store, _, _ = chat.get_stores()
    store.append_message("home", Message("user", "hello", 0.0))
    assert client.delete("/api/channels/home").status_code == 401
    assert store.get_channel("home") != []

    assert client.delete(
        "/api/channels/home", headers={"X-Gemini-Key": "k" * 30}
    ).json() == {"cleared": "home"}
    assert store.get_channel("home") == []
    assert client.get("/api/channels/home").json()["total"] == 0


def test_chat_with_an_ineligible_model_fails_closed(client):
    response = client.post(
        "/api/channels/home/chat",
        json={"message": "hi"},
        headers={"X-Gemini-Key": KEY, "X-Gemini-Model": "gemini-2.0-flash"},
    )
    assert response.status_code == 400
    assert "3.5" in response.json()["detail"]
