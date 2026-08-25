"""A failing tool answers the model instead of killing the turn."""
import asyncio

import pytest

from app import chat
from app.life import LifeAgent


@pytest.fixture
def organizer(monkeypatch, tmp_path):
    monkeypatch.setenv("CORONER_KNOWLEDGE_ROOT", str(tmp_path))
    chat.init_chat_stores(use_firestore=False)
    return chat._agent


def _tool(agent, name):
    return next(t for t in agent.agent.tools if t.__name__ == name)


def test_a_failing_write_returns_an_error_result_not_an_exception(organizer):
    class RejectingStore:
        def create_task(self, *args, **kwargs):
            raise ValueError("when must be an ISO-8601 date or datetime")

    organizer._store.set(RejectingStore())
    organizer._channel_id.set("home")
    organizer._created.set([])
    organizer._updated.set([])
    result = _tool(organizer, "create_task")(
        title="Assemble a new PC", when="friday this week"
    )
    assert result["error"] == "ValueError: when must be an ISO-8601 date or datetime"
    assert "hint" in result


def test_the_instruction_tells_the_model_what_day_it_is(organizer):
    _, task_store, _ = chat.get_stores()
    instruction = organizer.get_instruction(task_store)
    assert "Today is " in instruction
    assert "Asia/Jerusalem" in instruction


def test_a_voice_board_read_failure_answers_instead_of_raising():
    class ExplodingStore:
        def list_tasks(self, status=None):
            raise RuntimeError("restricted_resource")

    agent = LifeAgent()
    agent._store.set(ExplodingStore())
    result = _tool(agent, "list_tasks")()
    assert result["error"] == "RuntimeError: restricted_resource"
