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


def test_life_agent_is_a_pure_navigator():
    agent = LifeAgent(llm=ScriptedLifeLlm(model="gemini-3.7-flash"))
    assert _tool_names(agent) == ["send_task_to_chat", "navigate", "run_automation"]
    # Nothing that touches the board or the web may ever reach this agent;
    # every real action travels through the chat handoff.
    forbidden = {
        "create_task",
        "rename_task",
        "move_task",
        "list_tasks",
        "search_tasks",
        "read_task_details",
        "read_task_comments",
        "delete_task",
        "restore_task",
        "write_task_details",
        "add_task_comment",
        "plan_tomorrow",
        "web_research",
    }
    assert forbidden.isdisjoint(_tool_names(agent))


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
        # The handoff is fire-and-forget; wait for the spawned organizer run.
        await asyncio.gather(*live._pending)
        return result

    result = asyncio.run(run_and_settle())

    assert result["delivered"] is True
    # The organizer really executed the instruction against the board...
    [task] = tasks.list_tasks()
    assert task.title == "Call the accountant"
    # ...and the exchange landed in the chat like a typed turn.
    messages = channels.get_channel("home")
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].content == "Add a task to call the accountant"
    # Notified at handoff and again when the organizer finished.
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
    assert chat._live_voice_agent.prompt_source() == "Only navigate. Be terse."
    # Saving the untouched default clears the override.
    reset = client.put("/api/settings", json={"live_prompt": LIFE_PROMPT}).json()
    assert reset["live_prompt"] == LIFE_PROMPT
    assert chat._live_voice_agent.prompt_source() == ""

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
