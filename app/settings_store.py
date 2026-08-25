"""User-editable settings: chat prompt, live-voice speech, model API key.

Read per use rather than cached, so an edit reaches every Cloud Run instance
at once. ponytail: one document read next to an LLM call is free; add a TTL
cache only if the read ever shows up in a latency profile.
"""
from __future__ import annotations

from app.organizer import SYSTEM_PROMPT


class SettingsStore:
    def get_value(self, key: str, default=None):
        raise NotImplementedError

    def set_value(self, key: str, value) -> None:
        raise NotImplementedError

    def get_system_prompt(self) -> str:
        return self.get_value("system_prompt") or SYSTEM_PROMPT

    def set_system_prompt(self, prompt: str) -> None:
        self.set_value("system_prompt", prompt)


class LocalSettingsStore(SettingsStore):
    """Deterministic local/test store. Production uses Firestore."""

    def __init__(self) -> None:
        self.values: dict = {}

    def get_value(self, key: str, default=None):
        value = self.values.get(key)
        return default if value is None else value

    def set_value(self, key: str, value) -> None:
        self.values[key] = value


class FirestoreSettingsStore(SettingsStore):
    def __init__(self, db):
        self.document = db.collection("settings").document("organizer")

    def get_value(self, key: str, default=None):
        doc = self.document.get()
        value = (doc.to_dict() or {}).get(key) if doc.exists else None
        return default if value is None else value

    def set_value(self, key: str, value) -> None:
        self.document.set({key: value}, merge=True)
