"""General questions get a Google-Search-grounded answer through one tool."""

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
    return TestClient(api)


def test_the_tool_hands_the_question_to_the_grounded_call(client, monkeypatch):
    agent = chat._agent
    seen = []

    def fake_answer(query):
        seen.append(query)
        return {"answer": "It is 24 degrees.", "sources": [{"title": "x", "url": "https://x"}]}

    monkeypatch.setattr(agent, "_web_answer", fake_answer)
    tool = next(t for t in agent.agent.tools if t.__name__ == "web_search")
    token = agent._channel_id.set("task-chat")
    try:
        result = tool(query="Weather in Tel Aviv?")
    finally:
        agent._channel_id.reset(token)

    assert seen == ["Weather in Tel Aviv?"]
    assert result["answer"] == "It is 24 degrees."
    assert result["sources"][0]["url"] == "https://x"


def test_a_grounded_failure_is_a_readable_tool_result(client, monkeypatch):
    agent = chat._agent

    def boom(query):
        raise RuntimeError("grounding unavailable")

    monkeypatch.setattr(agent, "_web_answer", boom)
    tool = next(t for t in agent.agent.tools if t.__name__ == "web_search")
    token = agent._channel_id.set("task-chat")
    try:
        result = tool(query="anything")
    finally:
        agent._channel_id.reset(token)

    assert "error" in result
    assert "grounding unavailable" in result["error"]
