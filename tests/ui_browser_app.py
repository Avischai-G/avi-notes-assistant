"""Offline browser-test app with one scripted model tool choice."""
from __future__ import annotations

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from app import chat
from app.organizer import TaskOrganizerAgent as RealTaskOrganizerAgent


class BrowserPlanLlm(BaseLlm):
    """Create one task for the one documented browser-suite message."""

    _calls: int = PrivateAttr(default=0)

    async def generate_content_async(self, llm_request, stream=False):
        del llm_request, stream
        self._calls += 1
        if self._calls == 1:
            content = types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            name="create_task",
                            args={"title": "Print the contract", "place": "Office"},
                        )
                    )
                ],
            )
        else:
            content = types.Content(
                role="model", parts=[types.Part(text="Added Print the contract.")]
            )
        yield LlmResponse(content=content, partial=False)


def build_test_agent(*args, **kwargs):
    kwargs["llm"] = BrowserPlanLlm(model="gemini-3.5-flash")
    return RealTaskOrganizerAgent(*args, **kwargs)


chat.TaskOrganizerAgent = build_test_agent

from server import api  # noqa: E402


_, task_store, _ = chat.get_stores()
task_store.create_task(
    "Browser fixture Office task",
    place="Office",
    minutes=30,
    notes="Synthetic rendered-browser fixture",
)
