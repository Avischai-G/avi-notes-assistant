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
