"""The organizer remembers what the user asks it to, capped, and forgets on request."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import chat
from app.organizer import MEMORY_WORD_CAP


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORONER_KNOWLEDGE_ROOT", str(tmp_path))
    chat.init_chat_stores(use_firestore=False)
    api = FastAPI()
    chat.register_chat_routes(api)
    return TestClient(api)


def _tool(name: str):
    return next(tool for tool in chat._agent.agent.tools if tool.__name__ == name)


def test_remember_stores_and_the_prompt_carries_it(client):
    # An empty memory adds nothing to the prompt.
    assert "Stored memory" not in chat._agent.prompt_source()

    token = chat._agent._channel_id.set("task-chat")
    try:
        result = _tool("remember")(memory="Vegetarian. Prefers short answers.")
    finally:
        chat._agent._channel_id.reset(token)

    assert result == {"stored": True, "words": 4}
    prompt = chat._agent.prompt_source()
    assert prompt.endswith(
        "Stored memory about the user:\nVegetarian. Prefers short answers."
    )
    # The memory is a setting, so it survives an agent rebuild.
    chat._build_agents()
    assert "Vegetarian" in chat._agent.prompt_source()


def test_the_word_cap_refuses_an_oversized_memory(client):
    oversized = "word " * (MEMORY_WORD_CAP + 1)
    token = chat._agent._channel_id.set("task-chat")
    try:
        result = _tool("remember")(memory=oversized)
    finally:
        chat._agent._channel_id.reset(token)

    assert result["stored"] is False
    assert str(MEMORY_WORD_CAP) in result["reason"]
    assert "Condense" in result["reason"]
    # Nothing was written.
    assert chat._memory() == ""


def test_clear_memory_leaves_the_project_clean(client):
    token = chat._agent._channel_id.set("task-chat")
    try:
        _tool("remember")(memory="Handover: the old owner liked tea.")
        assert chat._memory() != ""
        result = _tool("clear_memory")()
    finally:
        chat._agent._channel_id.reset(token)

    assert result == {"cleared": True}
    assert chat._memory() == ""
    assert "Stored memory" not in chat._agent.prompt_source()
    assert chat._settings_store.get_value("memory") is None


def test_settings_edit_the_memory_with_the_same_cap(client):
    saved = client.put(
        "/api/settings", json={"memory": "  Vegetarian. Short answers.  "}
    )
    assert saved.status_code == 200
    assert saved.json()["memory"] == "Vegetarian. Short answers."
    assert chat._agent.prompt_source().endswith("Vegetarian. Short answers.")

    oversized = "word " * (MEMORY_WORD_CAP + 1)
    refused = client.put("/api/settings", json={"memory": oversized})
    assert refused.status_code == 400
    assert str(MEMORY_WORD_CAP) in refused.json()["detail"]
    assert chat._memory() == "Vegetarian. Short answers."

    cleared = client.put("/api/settings", json={"memory": ""})
    assert cleared.json()["memory"] == ""
    assert chat._settings_store.get_value("memory") is None


def test_the_voice_session_instructions_carry_the_memory(client):
    # The live navigator reads the same memory the chat writes.
    assert "Stored memory" not in chat._app_map()
    client.put("/api/settings", json={"memory": "Prefers tea."})
    assert chat._app_map().endswith("Stored memory about the user:\nPrefers tea.")


def test_switching_the_board_is_refused_offline_and_validates_the_id(client):
    # The offline fake store cannot point at Notion.
    refused = client.put(
        "/api/settings", json={"notion_database_id": "a" * 32}
    )
    assert refused.status_code == 400
    assert "offline" in refused.json()["detail"]

    malformed = client.put(
        "/api/settings", json={"notion_database_id": "not-a-database"}
    )
    assert malformed.status_code == 400
    assert "32-character" in malformed.json()["detail"]

    # Leaving the field as it is (empty here) changes nothing.
    assert client.put(
        "/api/settings", json={"notion_database_id": ""}
    ).status_code == 200

    # A token override follows the same offline refusal, and its format is
    # sanity-checked; the payload only ever says whether one is stored.
    assert client.get("/api/settings").json()["notion_token_set"] is False
    short = client.put("/api/settings", json={"notion_token": "nope"})
    assert short.status_code == 400
    assert "integration secret" in short.json()["detail"]
    offline_token = client.put(
        "/api/settings", json={"notion_token": "ntn_" + "a" * 40}
    )
    assert offline_token.status_code == 400
    assert "offline" in offline_token.json()["detail"]
    assert client.put("/api/settings", json={"notion_token": ""}).status_code == 200
