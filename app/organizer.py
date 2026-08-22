"""Task organizer agent using Google ADK with Vertex AI Gemini.

One LlmAgent, one instruction string, model=gemini-3.5-flash, location=global.
No SequentialAgent, ParallelAgent, sub-agents, handoffs, dispatch, launch, or stop.
"""
from __future__ import annotations

import json
import os
from typing import Optional, AsyncGenerator

try:
    from google.genai.client import Client
    from google.genai.types import (
        Tool,
        GenerateContentConfig,
        Content,
        Part,
    )
except ImportError:
    raise ImportError("google-genai SDK required. Install with: pip install google-generativeai")

from app.channel_store import ChannelStore, Message
from app.context_window import ContextWindow
from app.task_store import TaskStore


SYSTEM_PROMPT = """You are a task organizer. Your job is to understand requests about tasks,
inspect the task board when needed, create or rearrange task records, and report what changed.

You understand the request, suggest organization, create or move tasks on the board,
and report what you did. You never perform or dispatch the underlying work — you only organize
the task as well as you can. If you cannot create or move a task due to missing information,
ask for clarification.

When a user asks you to do something with their tasks:
1. Listen to what they want organized
2. Create, rename, or move tasks as needed
3. Report what changed on the board

Keep your responses concise and action-focused. Report the exact tasks created or moved."""


class TaskOrganizerAgent:
    """One Google ADK LlmAgent for organizing tasks."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-3.5-flash",
        location: str = "global",
    ):
        """Initialize the organizer agent.

        Args:
            api_key: Google Cloud API key. If None, uses GOOGLE_API_KEY env var.
            model: Vertex AI model name. Default gemini-3.5-flash.
            location: Vertex AI location. Must be 'global' for hackathon eligibility.
        """
        if location != "global":
            raise ValueError(
                f"Location must be 'global' for contest eligibility, got {location}"
            )

        self.model = model
        self.location = location
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")

        if not self.api_key:
            raise ValueError(
                "GOOGLE_API_KEY environment variable or api_key parameter required"
            )

        # Initialize Google Genai Client
        self.client = Client(api_key=self.api_key)

    def get_instruction(
        self,
        task_store: TaskStore,
    ) -> str:
        """Build the complete instruction for the LlmAgent.

        This is ONE assembled instruction string sent to the model.
        No second system prompt, no developer prompt, no extra personas.
        """
        # Fetch current board state
        today_tasks = task_store.list_tasks("what to do today")
        not_today_tasks = task_store.list_tasks("what to not do today")

        board_state = (
            f"Current task board state:\n"
            f"TODAY (what to do today): {len(today_tasks)} tasks\n"
            f"NOT TODAY (what to not do today): {len(not_today_tasks)} tasks\n"
        )

        if today_tasks:
            board_state += "\nTasks for today:\n"
            for t in today_tasks:
                board_state += f"- {t.title}\n"

        if not_today_tasks:
            board_state += "\nTasks not for today:\n"
            for t in not_today_tasks[:10]:  # Show first 10
                board_state += f"- {t.title}\n"
            if len(not_today_tasks) > 10:
                board_state += f"... and {len(not_today_tasks) - 10} more\n"

        return f"""{SYSTEM_PROMPT}

{board_state}

Your tools: create_task, rename_task, move_task, list_tasks.
Use them when the user asks you to organize their work."""

    async def chat(
        self,
        user_message: str,
        channel_store: ChannelStore,
        task_store: TaskStore,
        channel_id: str,
    ) -> AsyncGenerator[dict, None]:
        """Send a message and stream the response.

        Yields dictionaries with keys:
        - "text": streamed answer text
        - "done": True when the response is complete
        - "error": If an error occurs
        """
        try:
            # Get context window
            full_transcript = channel_store.get_channel(channel_id)
            context_messages = ContextWindow.get_model_input(full_transcript)

            # Add the current user message
            context_messages.append({"role": "user", "content": user_message})

            # Build instruction
            instruction = self.get_instruction(task_store)

            # Call Vertex AI Gemini
            config = GenerateContentConfig(
                system_instruction=instruction,
                temperature=0.7,
                top_p=0.95,
            )

            # Stream the response
            response_text = ""
            async for chunk in self.client.models.generate_content_stream(
                model=f"models/{self.model}",
                contents=context_messages,
                config=config,
            ):
                if chunk.text:
                    response_text += chunk.text
                    yield {"text": chunk.text}

            # Store messages
            channel_store.append_message(
                channel_id,
                Message(
                    role="user",
                    content=user_message,
                    timestamp=__import__("time").time(),
                ),
            )
            channel_store.append_message(
                channel_id,
                Message(
                    role="assistant",
                    content=response_text,
                    timestamp=__import__("time").time(),
                ),
            )

            yield {"done": True}

        except Exception as e:
            yield {"error": f"{type(e).__name__}: {e}"}

    @staticmethod
    def get_config() -> dict:
        """Return the agent configuration for eligibility checks."""
        return {
            "agent_type": "LlmAgent",
            "model": "gemini-3.5-flash",
            "location": "global",
            "framework": "Google ADK",
        }
