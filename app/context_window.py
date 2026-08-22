"""Manages the rolling context window for the organizer agent.

The newest 20 complete user turns and their assistant/tool events are sent to the model.
The full transcript stays loadable, but only the rolling window is in model input.
"""
from __future__ import annotations

from dataclasses import dataclass
from app.channel_store import Message


@dataclass
class ContextWindow:
    """Holds the rolling window of turns for model input."""

    MAX_TURNS = 20  # Complete user turns

    @staticmethod
    def get_model_input(messages: list[Message]) -> list[dict]:
        """Extract the newest 20 complete user turns (plus their assistant responses).

        This is what the model sees. The full transcript is preserved separately.
        Returns a list of OpenAI-compatible message dicts.
        """
        if not messages:
            return []

        # Find complete turns: each user message + subsequent assistant messages
        turns = []
        current_turn_messages = []

        for msg in messages:
            current_turn_messages.append(msg)
            # A turn is complete when we see the next user message
            if len(turns) == 0 or (len(current_turn_messages) > 1 and
                                   msg.role == "user"):
                if current_turn_messages[:-1]:  # Don't count the current user msg
                    turns.append(current_turn_messages[:-1])
                current_turn_messages = [msg]

        # Add the last incomplete turn if it has messages
        if current_turn_messages:
            turns.append(current_turn_messages)

        # Keep only the newest MAX_TURNS complete turns
        selected_turns = turns[-ContextWindow.MAX_TURNS:]

        # Flatten back to messages
        window_messages = []
        for turn in selected_turns:
            window_messages.extend(turn)

        # Convert to OpenAI format
        return [
            {
                "role": msg.role,
                "content": msg.content,
            }
            for msg in window_messages
        ]

    @staticmethod
    def count_user_turns(messages: list[Message]) -> int:
        """Count the number of user turns in the transcript."""
        return sum(1 for msg in messages if msg.role == "user")
