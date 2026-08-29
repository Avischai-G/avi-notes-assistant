"""Acceptance tests for the read-only life companion agent."""
from __future__ import annotations

import asyncio
import inspect

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from app.channel_store import LocalChannelStore
from app.life import LifeAgent
from app.task_store import FakeTaskStore


class ScriptedLifeLlm(BaseLlm):
    """One list_tasks call followed by one ordinary model response."""

    _calls: int = PrivateAttr(default=0)

    async def generate_content_async(self, llm_request, stream=False):
        self._calls += 1
        if self._calls == 1:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="list_tasks", args={}
                            )
                        )
                    ],
                ),
                partial=False,
            )
        else:
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text="Your board has one task.")]
                ),
                partial=False,
            )


def _tool_names(agent):
    return [
        getattr(tool, "name", None) or tool.__name__ for tool in agent.agent.tools
    ]


def test_the_voice_agent_reads_and_writes_the_shared_memory():
    agent = LifeAgent(llm=ScriptedLifeLlm(model="gemini-3.7-flash"))
    tools = {t.__name__: t for t in agent.agent.tools}
    # Outside a live session the tools fail honestly instead of crashing.
    assert tools["remember"](memory="tea drinker")["stored"] is False

    stored = []

    class FakeOrganizer:
        memory_sink = staticmethod(lambda text: stored.append(text))

    token = agent._bridge.set({"organizer": FakeOrganizer()})
    try:
        assert tools["remember"](memory="Prefers tea.") == {"stored": True, "words": 2}
        oversized = "word " * 200
        refused = tools["remember"](memory=oversized)
        assert refused["stored"] is False and "Condense" in refused["reason"]
        assert tools["clear_memory"]() == {"cleared": True}
    finally:
        agent._bridge.reset(token)
    # The same sink the chat writes through: one memory, shared by both.
    assert stored == ["Prefers tea.", ""]


def test_the_voice_agent_searches_the_web_through_the_organizer():
    agent = LifeAgent(llm=ScriptedLifeLlm(model="gemini-3.7-flash"))
    tool = next(t for t in agent.agent.tools if t.__name__ == "web_search")
    # Outside a live session the tool fails honestly instead of crashing.
    assert "error" in tool(query="fuel prices")

    class FakeOrganizer:
        def _web_answer(self, query):
            return {"answer": f"grounded: {query}", "sources": []}

    token = agent._bridge.set({"organizer": FakeOrganizer()})
    try:
        result = tool(query="fuel prices near me")
    finally:
        agent._bridge.reset(token)
    assert result == {"answer": "grounded: fuel prices near me", "sources": []}


def test_life_agent_reads_the_board_and_navigates_but_never_writes():
    agent = LifeAgent(llm=ScriptedLifeLlm(model="gemini-3.7-flash"))
    assert _tool_names(agent) == [
        "list_tasks",
        "search_tasks",
        "read_task_details",
        "read_task_comments",
        "web_search",
        "remember",
        "clear_memory",
        "send_task_to_chat",
        "wait_for_chat_answer",
        "navigate",
        "run_automation",
    ]
    # Nothing that mutates the board may ever reach this agent; every change
    # travels through the chat handoff.
    forbidden = {
        "create_task",
        "rename_task",
        "move_task",
        "delete_task",
        "restore_task",
        "write_task_details",
        "add_task_comment",
        "plan_tomorrow",
        "web_research",
    }
    assert forbidden.isdisjoint(_tool_names(agent))


def test_board_reads_answer_directly_without_writing():
    tasks = FakeTaskStore()
    tasks.create_task("Call the accountant")
    channels = LocalChannelStore()
    channels.ensure_channel("life-chat")
    agent = LifeAgent(llm=ScriptedLifeLlm(model="gemini-3.7-flash"))

    async def run():
        return [
            chunk
            async for chunk in agent.chat(
                "what's on my board?", channels, tasks, "life-chat"
            )
        ]

    chunks = asyncio.run(run())

    text = next(chunk["text"] for chunk in chunks if "text" in chunk)
    assert text == "Your board has one task."
    assert {c["tool"] for c in chunks if "tool" in c} == {"list_tasks"}
    # Only the test's own seed write touched the store.
    assert [op["action"] for op in tasks.operations] == ["create"]


def test_voice_memory_is_a_rolling_window(monkeypatch, tmp_path):
    from app import chat

    monkeypatch.setenv("TASK_STORE_MODE", "fake")
    monkeypatch.setenv("CORONER_KNOWLEDGE_ROOT", str(tmp_path / "k"))
    chat.init_chat_stores(use_firestore=False)

    assert chat._voice_memory_read("home") == []
    for index in range(12):
        chat._voice_memory_append(
            "home",
            [
                {"role": "user", "content": f"request {index}"},
                {"role": "assistant", "content": f"reply {index}"},
            ],
        )
    kept = chat._voice_memory_read("home")
    # Capped to the newest 8 exchanges (16 entries), oldest dropped.
    assert len(kept) == 16
    assert kept[0] == {"role": "user", "content": "request 4"}
    assert kept[-1] == {"role": "assistant", "content": "reply 11"}
    # Memory is per channel.
    assert chat._voice_memory_read("elsewhere") == []


def test_navigate_sends_a_frame_and_run_automation_resolves_names():
    live = LifeAgent(llm=ScriptedLifeLlm(model="gemini-live-2.5-flash"))
    frames = []
    starts = []

    async def send(frame):
        frames.append(frame)

    async def starter(name):
        starts.append(name)
        return {"started": True, "automation": name}

    navigate = next(t for t in live.agent.tools if t.__name__ == "navigate")
    run_automation = next(
        t for t in live.agent.tools if t.__name__ == "run_automation"
    )

    async def run():
        token = live._bridge.set(
            {
                "organizer": object(),
                "channel_store": None,
                "channel_id": "home",
                "notify": send,
                "send": send,
                "run_automation": starter,
            }
        )
        try:
            nav = await navigate(target=" settings ")
            auto = await run_automation(automation="Organize tasks")
            return nav, auto
        finally:
            live._bridge.reset(token)

    nav, auto = asyncio.run(run())
    assert nav == {"navigated": "settings"}
    assert frames == [{"type": "navigate", "target": "settings"}]
    assert auto == {"started": True, "automation": "Organize tasks"}
    assert starts == ["Organize tasks"]


def test_send_task_to_chat_hands_the_instruction_to_the_organizer():
    from test_assistant_behavior import ScriptedToolLlm
    from app.organizer import TaskOrganizerAgent

    tasks = FakeTaskStore()
    channels = LocalChannelStore()
    channels.ensure_channel("home")
    organizer = TaskOrganizerAgent(
        api_key="offline", llm=ScriptedToolLlm(model="gemini-3.5-flash")
    )
    live = LifeAgent(llm=ScriptedLifeLlm(model="gemini-live-2.5-flash"))
    notified = []

    async def notify():
        notified.append(True)

    tool = next(
        t for t in live.agent.tools if getattr(t, "__name__", "") == "send_task_to_chat"
    )

    async def run():
        store_token = live._store.set(tasks)
        bridge_token = live._bridge.set(
            {
                "organizer": organizer,
                "channel_store": channels,
                "channel_id": "home",
                "notify": notify,
            }
        )
        try:
            return await tool(instruction="Add a task to call the accountant")
        finally:
            live._bridge.reset(bridge_token)
            live._store.reset(store_token)

    async def run_and_settle():
        result = await run()
        # The background task may already be done; settle any stragglers.
        await asyncio.gather(*live._pending)
        return result

    result = asyncio.run(run_and_settle())

    assert result["delivered"] is True
    # A quick organizer reply is read back to the voice agent directly.
    assert result["answer"] == "Saved it."
    # The organizer really executed the instruction against the board...
    [task] = tasks.list_tasks()
    assert task.title == "Call the accountant"
    # ...and the exchange landed in the chat like a typed turn.
    messages = channels.get_channel("home")
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].content == "Add a task to call the accountant"
    # Notified twice: when the instruction lands, and with the answer.
    assert notified == [True, True]


def test_settings_roundtrip_voice_accent_and_api_key(monkeypatch, tmp_path):
    import os

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app import chat

    monkeypatch.setenv("TASK_STORE_MODE", "fake")
    monkeypatch.setenv("CORONER_KNOWLEDGE_ROOT", str(tmp_path / "k"))
    chat.init_chat_stores(use_firestore=False)
    api = FastAPI()
    chat.register_chat_routes(api)
    client = TestClient(api)

    base = client.get("/api/settings").json()
    assert "Puck" in base["voices"]
    # Keys are device-local; the server neither stores nor reports one.
    assert "api_key_set" not in base
    assert "gemini_api_key" not in base

    # The live prompt is visible (default until overridden) and editable.
    from app.life import LIFE_PROMPT

    assert base["live_prompt"] == LIFE_PROMPT
    edited = client.put(
        "/api/settings", json={"live_prompt": "Only navigate. Be terse."}
    ).json()
    assert edited["live_prompt"] == "Only navigate. Be terse."
    # The served prompt always ends by pointing at the Settings name field.
    assert chat._live_voice_agent.prompt_source() == (
        "Only navigate. Be terse."
    )
    # Saving the untouched default clears the override.
    reset = client.put("/api/settings", json={"live_prompt": LIFE_PROMPT}).json()
    assert reset["live_prompt"] == LIFE_PROMPT
    assert chat._live_voice_agent.prompt_source() == (
        LIFE_PROMPT
    )

    # No name field remains: the memory is the one place the agent knows things.
    assert "call_name" not in base
    assert "Avi" not in LIFE_PROMPT

    # One editable text carries role, style and rules; no separate rules field.
    assert "live_rules" not in base
    assert "Operating rules" in LIFE_PROMPT

    # Naming your languages narrows Automatic; clearing them lifts the limit.
    limited = client.put(
        "/api/settings", json={"live_languages": " Hebrew, German "}
    ).json()
    assert limited["live_languages"] == "Hebrew, German"
    assert chat._live_voice_agent.prompt_source().endswith(
        "The user speaks only these languages: Hebrew, German. Answer in "
        "whichever of them they are speaking; never use any other language."
    )
    cleared = client.put("/api/settings", json={"live_languages": ""}).json()
    assert cleared["live_languages"] == ""
    assert chat._live_voice_agent.prompt_source() == LIFE_PROMPT

    updated = client.put(
        "/api/settings", json={"voice_name": "Kore", "language_code": "en-GB"}
    ).json()
    assert (updated["voice_name"], updated["language_code"]) == ("Kore", "en-GB")
    assert chat._live_voice_agent.speech_settings() == {
        "voice_name": "Kore",
        "language_code": "en-GB",
    }

    # A stored key sent by an old client is ignored, never persisted.
    client.put("/api/settings", json={"gemini_api_key": "AIza" + "x" * 30})
    assert chat._settings_store.get_value("gemini_api_key") is None
    assert "GOOGLE_API_KEY" not in os.environ

    assert client.put("/api/settings", json={"voice_name": "NotAVoice"}).status_code == 400
    assert client.put("/api/settings", json={"language_code": "bad!"}).status_code == 400


def test_device_key_header_selects_a_cached_per_key_agent(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app import chat

    monkeypatch.setenv("TASK_STORE_MODE", "fake")
    monkeypatch.setenv("CORONER_KNOWLEDGE_ROOT", str(tmp_path / "k"))
    chat.init_chat_stores(use_firestore=False)
    api = FastAPI()
    chat.register_chat_routes(api)
    client = TestClient(api)

    default_agent = chat._agent
    key = "AIza" + "d" * 30
    organizer_a, live_a = chat._agents_for_request_key(key)
    organizer_b, live_b = chat._agents_for_request_key(key)
    # Same key → same cached pair, distinct from the server-credential agents.
    assert organizer_a is organizer_b and live_a is live_b
    assert organizer_a is not default_agent
    assert live_a.model == "gemini-live-2.5-flash"  # voice always runs on Vertex
    # Rejected before any model call; nothing about the key is stored.
    response = client.post(
        "/api/channels/x/chat",
        json={"message": "hi"},
        headers={"X-Gemini-Key": "not a key!!"},
    )
    assert response.status_code == 400
    assert chat._settings_store.get_value("gemini_api_key") is None


def test_live_voice_route_is_registered_and_live_models_construct():
    from app import chat

    source = inspect.getsource(chat.register_chat_routes)
    assert "def live_session(" in source
    assert '"/api/live/{channel_id}"' in source

    # The live-audio model family passes the guard; the research sub-agent
    # stays on the text model.
    agent = LifeAgent(
        model="gemini-live-2.5-flash",
        llm=ScriptedLifeLlm(model="gemini-live-2.5-flash"),
    )
    assert agent.model == "gemini-live-2.5-flash"
    assert hasattr(agent, "live_bridge")
