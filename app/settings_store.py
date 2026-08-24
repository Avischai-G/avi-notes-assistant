"""The one user-editable setting: the chat's system prompt.

Read per turn rather than cached, so an edit reaches every Cloud Run instance
at once. ponytail: one document read next to an LLM call is free; add a TTL
cache only if the read ever shows up in a latency profile.
"""
from __future__ import annotations

from app.organizer import SYSTEM_PROMPT


class SettingsStore:
    def get_system_prompt(self) -> str:
        raise NotImplementedError

    def set_system_prompt(self, prompt: str) -> None:
        raise NotImplementedError


class LocalSettingsStore(SettingsStore):
    """Deterministic local/test store. Production uses Firestore."""

    def __init__(self) -> None:
        self.system_prompt = SYSTEM_PROMPT

    def get_system_prompt(self) -> str:
        return self.system_prompt

    def set_system_prompt(self, prompt: str) -> None:
        self.system_prompt = prompt


class FirestoreSettingsStore(SettingsStore):
    def __init__(self, db):
        self.document = db.collection("settings").document("organizer")

    def get_system_prompt(self) -> str:
        doc = self.document.get()
        stored = (doc.to_dict() or {}).get("system_prompt") if doc.exists else None
        return stored or SYSTEM_PROMPT

    def set_system_prompt(self, prompt: str) -> None:
        self.document.set({"system_prompt": prompt})
