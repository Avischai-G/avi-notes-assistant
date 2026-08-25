"""The voice agent's handoff: quick answers return, slow ones can be awaited."""
import asyncio

import app.life as life
from app.life import LifeAgent


def _tools(agent):
    return {
        getattr(tool, "__name__", ""): tool
        for tool in agent.agent.tools
    }


def _wire(agent, organizer_chat):
    class Organizer:
        chat = staticmethod(organizer_chat)

    agent._store.set(None)
    agent._bridge.set(
        {
            "organizer": Organizer(),
            "channel_store": None,
            "channel_id": "home",
            "notify": _noop,
        }
    )


async def _noop():
    return None


def test_a_quick_answer_comes_straight_back():
    agent = LifeAgent()
    tools = _tools(agent)

    def chat(instruction, channel_store, task_store, channel_id):
        async def stream():
            yield {"text": f"Done: {instruction}"}

        return stream()

    async def scenario():
        _wire(agent, chat)
        return await tools["send_task_to_chat"]("Buy tea")

    result = asyncio.run(scenario())
    assert result == {"delivered": True, "answer": "Done: Buy tea"}


def test_a_slow_answer_is_pending_then_awaited(monkeypatch):
    monkeypatch.setattr(life, "QUICK_WAIT_SECONDS", 0.05)
    agent = LifeAgent()
    tools = _tools(agent)

    def chat(instruction, channel_store, task_store, channel_id):
        async def stream():
            await asyncio.sleep(0.2)
            yield {"text": "Finally done."}

        return stream()

    async def scenario():
        _wire(agent, chat)
        sent = await tools["send_task_to_chat"]("Slow thing")
        awaited = await tools["wait_for_chat_answer"]()
        return sent, awaited

    sent, awaited = asyncio.run(scenario())
    assert sent["answer_pending"] is True
    assert "wait_for_chat_answer" in sent["note"]
    assert awaited == {"answer": "Finally done."}


def test_waiting_with_nothing_pending_says_so():
    agent = LifeAgent()
    tools = _tools(agent)

    async def scenario():
        agent._bridge.set({"organizer": None})
        return await tools["wait_for_chat_answer"]()

    result = asyncio.run(scenario())
    assert result["note"] == "Nothing was handed to the chat yet."
