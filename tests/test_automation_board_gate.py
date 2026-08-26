"""Automation channels use the same tools as chat; only two doors stay shut:
an unknown channel identity fails closed, and an automation never starts
another automation."""

from __future__ import annotations

import asyncio

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr
import pytest

from app.channel_store import LocalChannelStore
from app.notion_mcp import NotionConfig
from app.notion_task_store import NotionTaskStore
from app.organizer import SYSTEM_PROMPT, TaskOrganizerAgent
from app.task_store import FakeTaskStore


class SpyNotionClient:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def execute(self, operation, payload):
        self.calls.append((operation, payload))
        raise AssertionError("Notion HTTP path must not be reached")

    def close(self):
        pass


class AttemptBoardToolLlm(BaseLlm):
    tool_name: str
    tool_args: dict
    _calls: int = PrivateAttr(default=0)

    async def generate_content_async(self, llm_request, stream=False):
        del llm_request, stream
        self._calls += 1
        if self._calls == 1:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name=self.tool_name,
                                args=self.tool_args,
                            )
                        )
                    ],
                ),
                partial=False,
            )
        else:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="Automation turn finished.")],
                ),
                partial=False,
            )


async def run_attempt(tool_name: str, tool_args: dict, channel_id: str, store):
    channels = LocalChannelStore()
    channels.ensure_channel(channel_id)
    model = AttemptBoardToolLlm(
        model="gemini-3.5-flash",
        tool_name=tool_name,
        tool_args=tool_args,
    )
    agent = TaskOrganizerAgent(api_key="offline", llm=model)
    chunks = [
        chunk
        async for chunk in agent.chat(
            "Look after the board.",
            channels,
            store,
            channel_id,
        )
    ]
    return chunks, channels.get_channel(channel_id)


@pytest.mark.parametrize(
    "tool_name,tool_args,check",
    [
        (
            "create_task",
            {"title": "Buy printer paper"},
            lambda store, result: store.list_tasks()[0].title == "Buy printer paper"
            and result["created"]["name"] == "Buy printer paper",
        ),
        (
            "list_tasks",
            {},
            lambda store, result: result == {"tasks": []},
        ),
    ],
)
def test_automation_channel_uses_board_tools_like_chat(tool_name, tool_args, check):
    store = FakeTaskStore()
    chunks, history = asyncio.run(
        run_attempt(tool_name, tool_args, "automation-organize-tasks", store)
    )

    assert not any("error" in chunk for chunk in chunks)
    assert {"tool": tool_name, "status": "completed"} in chunks
    [tool_result] = history[-1].tool_results
    assert tool_result["name"] == tool_name
    assert "refused" not in tool_result["response"]
    assert check(store, tool_result["response"])


def test_an_automation_cannot_start_another_automation():
    store = FakeTaskStore()
    chunks, history = asyncio.run(
        run_attempt(
            "run_automation",
            {"name": "Organize tasks"},
            "automation-organize-tasks",
            store,
        )
    )

    assert not any("error" in chunk for chunk in chunks)
    [tool_result] = history[-1].tool_results
    assert tool_result["response"]["refused"] is True
    assert "cannot start another automation" in tool_result["response"]["reason"]
    assert "do not retry" in tool_result["response"]["reason"]


def test_unknown_channel_context_fails_closed_without_notion_call():
    agent = TaskOrganizerAgent(
        api_key="offline",
        llm=AttemptBoardToolLlm(
            model="gemini-3.5-flash",
            tool_name="create_task",
            tool_args={"title": "Out-of-scope task"},
        ),
    )
    notion = SpyNotionClient()
    store = NotionTaskStore(
        NotionConfig(token="offline", tasks_database_id="a" * 32),
        notion,
    )
    store_token = agent._store.set(store)
    created_token = agent._created.set([])
    message_token = agent._message.set("unknown channel")
    try:
        result = agent.agent.tools[0](title="Out-of-scope task")
    finally:
        agent._message.reset(message_token)
        agent._created.reset(created_token)
        agent._store.reset(store_token)

    assert result["refused"] is True
    assert "do not retry" in result["reason"]
    assert notion.calls == []
    assert len(SYSTEM_PROMPT.split()) <= 400
