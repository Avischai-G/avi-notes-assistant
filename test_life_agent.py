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


def test_life_agent_tools_are_read_only_plus_web_research():
    agent = LifeAgent(llm=ScriptedLifeLlm(model="gemini-3.7-flash"))
    assert _tool_names(agent) == [
        "list_tasks",
        "search_tasks",
        "read_task_details",
        "read_task_comments",
        "web_research",
    ]
    # No board-mutating tool may ever reach this agent.
    forbidden = {
        "create_task",
        "rename_task",
        "move_task",
        "delete_task",
        "restore_task",
        "write_task_details",
        "add_task_comment",
        "plan_tomorrow",
    }
    assert forbidden.isdisjoint(_tool_names(agent))


def test_life_turn_reads_the_board_and_writes_nothing():
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
    tool_events = [chunk for chunk in chunks if "tool" in chunk]
    assert {event["tool"] for event in tool_events} == {"list_tasks"}
    # Only the test's own seed write touched the store.
    assert [op["action"] for op in tasks.operations] == ["create"]
    messages = channels.get_channel("life-chat")
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].content == "Your board has one task."


def test_life_endpoint_is_registered():
    from app import chat

    source = inspect.getsource(chat.register_chat_routes)
    assert "def life_chat(" in source
    assert '"/api/channels/{channel_id}/life"' in source
