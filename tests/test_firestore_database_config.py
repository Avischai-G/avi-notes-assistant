"""The production Firestore client always targets an explicit Native database."""

from __future__ import annotations

import pytest

from app import chat


class CapturingFirestore:
    def __init__(self):
        self.calls = []
        self.client = object()

    def Client(self, **kwargs):
        self.calls.append(kwargs)
        return self.client


def test_firestore_client_defaults_to_coroner(monkeypatch):
    factory = CapturingFirestore()
    monkeypatch.setattr(chat, "firestore", factory)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.delenv("FIRESTORE_DATABASE", raising=False)

    assert chat._create_firestore_client() is factory.client
    assert factory.calls == [
        {"project": "test-project", "database": "coroner"}
    ]


def test_firestore_client_uses_configured_database(monkeypatch):
    factory = CapturingFirestore()
    monkeypatch.setattr(chat, "firestore", factory)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("FIRESTORE_DATABASE", "another-native-database")

    chat._create_firestore_client()

    assert factory.calls == [
        {"project": "test-project", "database": "another-native-database"}
    ]


def test_blank_firestore_database_fails_closed(monkeypatch):
    factory = CapturingFirestore()
    monkeypatch.setattr(chat, "firestore", factory)
    monkeypatch.setenv("FIRESTORE_DATABASE", "   ")

    with pytest.raises(RuntimeError, match="FIRESTORE_DATABASE must be non-empty"):
        chat._create_firestore_client()
    assert factory.calls == []


def test_firestore_client_error_is_not_downgraded(monkeypatch):
    class UnreachableFirestore:
        @staticmethod
        def Client(**_kwargs):
            raise ConnectionError("Firestore unavailable")

    monkeypatch.setattr(chat, "firestore", UnreachableFirestore())
    monkeypatch.delenv("FIRESTORE_DATABASE", raising=False)

    with pytest.raises(ConnectionError, match="Firestore unavailable"):
        chat._create_firestore_client()
