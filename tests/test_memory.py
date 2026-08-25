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
