"""Durable channel transcript storage, backed by Firestore in production."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class Message:
    """A single message in a channel transcript."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float
    tool_calls: list[dict] | None = None
    tool_results: list[dict] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ChannelStore:
    """Interface for durable channel transcripts."""

    def get_channel(self, channel_id: str) -> list[Message]:
        """Load full transcript for a channel. Overridden in production."""
        raise NotImplementedError

    def append_message(self, channel_id: str, message: Message) -> None:
        """Append a message to a channel. Overridden in production."""
        raise NotImplementedError

    def create_channel(self, channel_id: str | None = None) -> str:
        """Create a new channel. Returns the channel ID."""
        raise NotImplementedError

    def ensure_channel(self, channel_id: str) -> str:
        """Create only when absent; restart-safe stable channel binding."""
        if not self.get_channel(channel_id):
            return self.create_channel(channel_id)
        return channel_id


class LocalChannelStore(ChannelStore):
    """Deterministic local test store. Production uses Firestore."""

    def __init__(self):
        self.channels: dict[str, list[Message]] = {}

    def get_channel(self, channel_id: str) -> list[Message]:
        return self.channels.get(channel_id, [])

    def append_message(self, channel_id: str, message: Message) -> None:
        if channel_id not in self.channels:
            self.channels[channel_id] = []
        self.channels[channel_id].append(message)

    def create_channel(self, channel_id: str | None = None) -> str:
        if channel_id is None:
            channel_id = str(uuid.uuid4())
        self.channels[channel_id] = []
        return channel_id

    def ensure_channel(self, channel_id: str) -> str:
        self.channels.setdefault(channel_id, [])
        return channel_id


class FirestoreChannelStore(ChannelStore):
    """Production Firestore-backed store."""

    def __init__(self, db):
        self.db = db

    def get_channel(self, channel_id: str) -> list[Message]:
        """Load full transcript from Firestore."""
        doc = self.db.collection("channels").document(channel_id).get()
        if not doc.exists:
            return []
        data = doc.to_dict() or {}
        messages = data.get("messages", [])
        return [
            Message(
                role=m["role"],
                content=m["content"],
                timestamp=m["timestamp"],
                tool_calls=m.get("tool_calls"),
                tool_results=m.get("tool_results"),
            )
            for m in messages
        ]

    def append_message(self, channel_id: str, message: Message) -> None:
        """Append a message to the Firestore transcript."""
        doc_ref = self.db.collection("channels").document(channel_id)
        # Get current messages
        doc = doc_ref.get()
        messages = doc.to_dict().get("messages", []) if doc.exists else []
        # Append new message
        messages.append(message.to_dict())
        # Write back
        doc_ref.set({
            "messages": messages,
            "updated_at": datetime.utcnow(),
        })

    def create_channel(self, channel_id: str | None = None) -> str:
        """Create a new channel in Firestore."""
        if channel_id is None:
            channel_id = str(uuid.uuid4())
        self.db.collection("channels").document(channel_id).set({
            "messages": [],
            "created_at": datetime.utcnow(),
        })
        return channel_id

    def ensure_channel(self, channel_id: str) -> str:
        ref = self.db.collection("channels").document(channel_id)
        if not ref.get().exists:
            self.create_channel(channel_id)
        return channel_id
