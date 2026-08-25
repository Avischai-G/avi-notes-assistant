"""A photo sent with a message can land on a task's page, served by the app."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import chat


PNG = b"\x89PNG\r\n\x1a\nfakepixels"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORONER_KNOWLEDGE_ROOT", str(tmp_path))
    chat.init_chat_stores(use_firestore=False)
    api = FastAPI()
    chat.register_chat_routes(api)
    return TestClient(api)


def _tool(name: str):
    return next(tool for tool in chat._agent.agent.tools if tool.__name__ == name)


def _turn_tokens(task_store, attachments):
    agent = chat._agent
    return [
        (agent._channel_id, agent._channel_id.set("task-chat")),
        (agent._store, agent._store.set(task_store)),
        (agent._attachments, agent._attachments.set(attachments)),
    ]


def test_attach_files_writes_the_task_body_and_serves_the_file(client, tmp_path):
    chat._request_origin.set("https://example.app")
    _, task_store, _ = chat.get_stores()
    task = task_store.create_task("Print the poster", "Not started")

    tokens = _turn_tokens(task_store, [("image/png", PNG)])
    try:
        result = _tool("attach_files_to_task")(task_id=task.id)
    finally:
        for var, token in reversed(tokens):
            var.reset(token)

    assert result == {"attached": True, "files": 1}
    body = task_store.get_task_body(task.id)
    assert body.startswith("![attachment](https://example.app/files/")
    name = body.rsplit("/files/", 1)[1].rstrip(")")
    assert (tmp_path / "attachments" / name).read_bytes() == PNG

    served = client.get(f"/files/{name}")
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/png")
    assert served.content == PNG


def test_a_turn_without_files_reports_it_instead_of_writing(client):
    _, task_store, _ = chat.get_stores()
    task = task_store.create_task("No photo here", "Not started")

    tokens = _turn_tokens(task_store, [])
    try:
        result = _tool("attach_files_to_task")(task_id=task.id)
    finally:
        for var, token in reversed(tokens):
            var.reset(token)

    assert result["attached"] is False
    assert "no attached files" in result["reason"]
    assert task_store.get_task_body(task.id) == ""


def test_the_file_route_serves_only_stored_handles(client):
    assert client.get("/files/notahex.png").status_code == 404
    assert client.get("/files/" + "a" * 32 + ".png").status_code == 404
