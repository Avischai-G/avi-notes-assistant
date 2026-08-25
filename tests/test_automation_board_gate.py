"""Automation channels cannot reach any board tool or its Notion client."""

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
                    parts=[types.Part(text="Finished without board access.")],
                ),
                partial=False,
            )


async def run_attempt(tool_name: str, tool_args: dict, channel_id: str):
    notion = SpyNotionClient()
    store = NotionTaskStore(
        NotionConfig(token="offline", tasks_database_id="a" * 32),
        notion,
    )
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
            "Clean up private knowledge.",
            channels,
            store,
            channel_id,
        )
    ]
    return chunks, channels.get_channel(channel_id), notion.calls


@pytest.mark.parametrize(
    "tool_name,tool_args",
    [
        ("create_task", {"title": "Out-of-scope task"}),
        ("rename_task", {"task_id": "page", "new_title": "Out-of-scope rename"}),
        ("move_task", {"task_id": "page", "status": "Done"}),
        ("list_tasks", {}),
        # An automation must not be able to set another one running.
        ("list_automations", {}),
        ("run_automation", {"name": "Organize tasks"}),
    ],
)
def test_automation_channel_refuses_every_board_tool_without_notion_call(
    tool_name, tool_args
):
    chunks, history, notion_calls = asyncio.run(
        run_attempt(tool_name, tool_args, "automation-organize-tasks")
    )

    assert notion_calls == []
    assert not any("error" in chunk for chunk in chunks)
    assert {"tool": tool_name, "status": "completed"} in chunks
    assert chunks[-2:] == [
        {"text": "Finished without board access."},
        {"done": True},
    ]
    [tool_result] = history[-1].tool_results
    assert tool_result["name"] == tool_name
    assert tool_result["response"]["refused"] is True
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
    assert notion.calls == []
    assert len(SYSTEM_PROMPT.split()) <= 260
