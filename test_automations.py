"""Offline acceptance tests for persistent automation channels."""
import asyncio
from datetime import datetime

from app.automations import Automation, AutomationRunner, LocalAutomationStore
from app.channel_store import LocalChannelStore
from app.task_planning import JERUSALEM


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


def make(name, channel):
    return Automation(name, name, f"Prompt for {name}", "daily", True, channel)


def test_persistent_and_isolated_channels():
    channels, agent = LocalChannelStore(), FakeAgent()
    a, b = make("a", "channel-a"), make("b", "channel-b")
    channels.ensure_channel(a.channel_id); channels.ensure_channel(b.channel_id)
    store = LocalAutomationStore([a, b])
    runner = AutomationRunner(store, channels, object(), agent)
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


def test_a_trigger_decides_the_next_run(monkeypatch):
    """Every automation is due by its own trigger; nothing is special-cased."""
    channels, agent = LocalChannelStore(), FakeAgent()
    a = make("hourly-note", "channel-h")
    a.frequency, a.minute = "hourly", 30
    channels.ensure_channel(a.channel_id)
    store = LocalAutomationStore([a])
    # Monday 2026-08-24, 09:00 Jerusalem.
    now = datetime(2026, 8, 24, 9, 0, tzinfo=JERUSALEM).timestamp()
    runner = AutomationRunner(store, channels, object(), agent, clock=lambda: now)

    asyncio.run(runner.run("hourly-note"))
    saved = store.get("hourly-note")
    assert saved.next_run_at == now + 30 * 60

    # Not due until that moment arrives, and a forced run ignores the trigger.
    assert asyncio.run(runner.run("hourly-note", force=False))["status"] == "not-due"
    assert asyncio.run(runner.run("hourly-note"))["status"] == "ran"


if __name__ == "__main__":
    for name, value in list(globals().items()):
        if name.startswith("test_"):
            value(); print("PASS", name)
