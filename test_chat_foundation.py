"""Tests for the task-organizer chat foundation.

Verifies:
1. One ADK LlmAgent with gemini-3.5-flash at global location
2. /api/health reports eligibility
3. Transcript storage and recovery
4. Rolling context window (newest 20 turns)
"""
import pytest
import asyncio
import time
import json
from unittest.mock import MagicMock, AsyncMock, patch

from app.channel_store import LocalChannelStore, Message
from app.context_window import ContextWindow
from app.task_store import FakeTaskStore
from app.organizer import TaskOrganizerAgent


def test_adk_agent_single_llm_agent():
    """Verify exactly one LlmAgent, model=gemini-3.5-flash, location=global."""
    with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
        agent = TaskOrganizerAgent(
            api_key='test-key',
            model='gemini-3.5-flash',
            location='global'
        )

        config = agent.get_config()
        assert config['agent_type'] == 'LlmAgent'
        assert config['model'] == 'gemini-3.5-flash'
        assert config['location'] == 'global'
        assert config['framework'] == 'Google ADK'


def test_agent_rejects_non_global_location():
    """Verify agent rejects non-global locations."""
    with pytest.raises(ValueError, match="must be 'global'"):
        TaskOrganizerAgent(
            api_key='test-key',
            model='gemini-3.5-flash',
            location='us-central1'
        )


def test_channel_store_local():
    """Test LocalChannelStore message append and retrieval."""
    store = LocalChannelStore()

    # Create channel
    channel_id = store.create_channel()
    assert channel_id
    assert store.get_channel(channel_id) == []

    # Append message
    msg = Message(
        role='user',
        content='Hello',
        timestamp=time.time()
    )
    store.append_message(channel_id, msg)

    # Retrieve
    messages = store.get_channel(channel_id)
    assert len(messages) == 1
    assert messages[0].role == 'user'
    assert messages[0].content == 'Hello'


def test_context_window_newest_20_turns():
    """Test that context window returns newest 20 complete user turns."""
    store = LocalChannelStore()
    channel_id = store.create_channel()

    # Create 21 user turns with responses
    for i in range(21):
        store.append_message(channel_id, Message(
            role='user',
            content=f'Turn {i}',
            timestamp=time.time() + i
        ))
        store.append_message(channel_id, Message(
            role='assistant',
            content=f'Response {i}',
            timestamp=time.time() + i + 0.1
        ))

    # Load full transcript
    full = store.get_channel(channel_id)
    assert len(full) == 42  # 21 pairs

    # Get model input (should have newest 20 turns = 40 messages)
    model_input = ContextWindow.get_model_input(full)

    # Should have 40 messages (20 user + 20 assistant)
    assert len(model_input) == 40

    # First user message should be Turn 1 (not Turn 0)
    user_messages = [m for m in model_input if m['role'] == 'user']
    assert user_messages[0]['content'] == 'Turn 1'
    assert user_messages[-1]['content'] == 'Turn 20'

    # Full history still has 42 (all 21 turns)
    assert len(full) == 42


def test_task_store_operations():
    """Test FakeTaskStore create, rename, move."""
    store = FakeTaskStore()

    # Create task
    task = store.create_task('Buy milk', lane='Not started')
    assert task.title == 'Buy milk'
    assert task.lane == 'Not started'

    # List tasks
    not_started = store.list_tasks('Not started')
    assert len(not_started) == 1
    assert not_started[0].title == 'Buy milk'

    # Rename task
    store.rename_task(task.id, 'Buy organic milk')
    tasks = store.list_tasks()
    assert tasks[0].title == 'Buy organic milk'

    # Move task
    store.move_task(task.id, 'In progress')
    in_progress = store.list_tasks('In progress')
    assert len(in_progress) == 1
    assert in_progress[0].title == 'Buy organic milk'

    # Verify operations recorded
    assert len(store.operations) == 3


def test_transcript_persistence_and_recovery():
    """Test that a full transcript survives storage and retrieval."""
    store = LocalChannelStore()
    channel_id = store.create_channel()

    # Add alternating user/assistant messages
    messages = [
        Message(role='user', content='Question 1', timestamp=1.0),
        Message(role='assistant', content='Answer 1', timestamp=1.1),
        Message(role='user', content='Question 2', timestamp=2.0),
        Message(role='assistant', content='Answer 2', timestamp=2.1),
    ]

    for msg in messages:
        store.append_message(channel_id, msg)

    # Retrieve and verify
    retrieved = store.get_channel(channel_id)
    assert len(retrieved) == 4

    assert retrieved[0].role == 'user'
    assert retrieved[0].content == 'Question 1'

    assert retrieved[3].role == 'assistant'
    assert retrieved[3].content == 'Answer 2'


def test_health_endpoint_config(monkeypatch, tmp_path):
    """Exercise the real route and the actual initialized agent values."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import chat

    monkeypatch.setenv("TASK_STORE_MODE", "fake")
    monkeypatch.setenv("CORONER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    chat.init_chat_stores(use_firestore=False)
    app = FastAPI()
    chat.register_chat_routes(app)
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    config = response.json()
    assert config['model'] == 'gemini-3.5-flash'
    assert config['location'] == 'global'
    assert config['framework'] == 'Google ADK'
    assert config['firestore_mode'] == 'local'


def test_no_agent_orchestration_tools():
    """Verify the organizer has no dispatch/launch/stop tools."""
    with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
        agent = TaskOrganizerAgent(api_key='test-key')

        # Get the instruction - it should mention organize, not execute
        instruction = agent.get_instruction(FakeTaskStore())

        # Should contain organizing language
        assert 'organize' in instruction.lower()
        assert 'task' in instruction.lower()

        # Should NOT mention execution/dispatch
        assert 'dispatch' not in instruction.lower()
        assert 'execute' not in instruction.lower()
        assert 'launch' not in instruction.lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
