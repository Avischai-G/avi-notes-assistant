"""Offline acceptance tests for persistent automation channels."""
import asyncio
from app.automations import Automation, AutomationRunner, LocalAutomationStore
from app.channel_store import LocalChannelStore


class FakeAgent:
    def __init__(self): self.calls = []
    async def chat(self, user_message, channel_store, task_store, channel_id):
        self.calls.append((user_message, channel_id))
        # Match the real agent's storage behavior for this test double.
        from app.channel_store import Message
        channel_store.append_message(channel_id, Message("user", user_message, 1.0))
        channel_store.append_message(channel_id, Message("assistant", "organized", 1.0))
        yield {"text": "organized"}
        yield {"done": True}


class Dreams:
    def __init__(self, present): self.present, self.consolidations = present, 0
    def has_dreams(self): return self.present
    def consolidate(self):
        self.consolidations += 1
        return {"summary": "one consolidated skill", "learning_event": True}


def make(name, channel):
    return Automation(name, name, f"Prompt for {name}", "daily", True, channel)


def test_persistent_and_isolated_channels():
    channels, agent = LocalChannelStore(), FakeAgent()
    a, b = make("a", "channel-a"), make("b", "channel-b")
    channels.ensure_channel(a.channel_id); channels.ensure_channel(b.channel_id)
    store = LocalAutomationStore([a, b])
    runner = AutomationRunner(store, channels, object(), agent, Dreams(False))
    asyncio.run(runner.run("a")); asyncio.run(runner.run("a"))
    assert [x[1] for x in agent.calls] == ["channel-a", "channel-a"]
    assert all("Prompt for a" in x[0] for x in agent.calls)
    assert channels.get_channel("channel-b") == []
    assert len(channels.get_channel("channel-a")) == 4


def test_restart_keeps_channel_and_transcript():
    channels = LocalChannelStore(); channels.ensure_channel("stable")
    from app.channel_store import Message
    channels.append_message("stable", Message("user", "old", 1.0))
    channels.ensure_channel("stable")
    assert [m.content for m in channels.get_channel("stable")] == ["old"]


def test_no_dreams_skips_model():
    channels, agent, knowledge = LocalChannelStore(), FakeAgent(), Dreams(False)
    a = make("knowledge-cleanup", "cleanup")
    channels.ensure_channel(a.channel_id)
    result = asyncio.run(AutomationRunner(LocalAutomationStore([a]), channels, object(), agent, knowledge).run(a.id))
    assert result["status"] == "no-work" and result["model_called"] is False
    assert agent.calls == []
    assert [message.content for message in channels.get_channel("cleanup")] == [
        "No dream notes to consolidate."
    ]


def test_dream_cleanup_records_learning_context():
    channels, agent, knowledge = LocalChannelStore(), FakeAgent(), Dreams(True)
    a = make("knowledge-cleanup", "cleanup")
    channels.ensure_channel(a.channel_id)
    result = asyncio.run(AutomationRunner(LocalAutomationStore([a]), channels, object(), agent, knowledge).run(a.id))
    assert result["status"] == "ran" and knowledge.consolidations == 1
    assert "learning_event" in agent.calls[0][0]
    assert agent.calls[0][1] == "cleanup"


if __name__ == "__main__":
    for name, value in list(globals().items()):
        if name.startswith("test_"):
            value(); print("PASS", name)
