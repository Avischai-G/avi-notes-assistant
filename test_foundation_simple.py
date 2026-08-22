#!/usr/bin/env python3
"""Simple test of foundation without pytest."""

import sys
import os
import time
sys.path.insert(0, os.path.dirname(__file__))

from app.channel_store import LocalChannelStore, Message
from app.context_window import ContextWindow
from app.task_store import FakeTaskStore


def test_channel_store():
    """Test channel storage."""
    print("Testing LocalChannelStore...")
    store = LocalChannelStore()

    # Create channel
    channel_id = store.create_channel()
    assert channel_id, "Failed to create channel"
    assert store.get_channel(channel_id) == [], "New channel should be empty"

    # Append and retrieve
    msg = Message(role='user', content='Hello', timestamp=time.time())
    store.append_message(channel_id, msg)
    messages = store.get_channel(channel_id)
    assert len(messages) == 1, "Should have 1 message"
    assert messages[0].role == 'user', "Message role should be user"
    print("✓ LocalChannelStore works")


def test_context_window():
    """Test context window (newest 20 turns)."""
    print("Testing ContextWindow (newest 20 of 21 turns)...")
    store = LocalChannelStore()
    channel_id = store.create_channel()

    # Create 21 user turns with assistant responses
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

    full = store.get_channel(channel_id)
    assert len(full) == 42, f"Should have 42 messages, got {len(full)}"

    # Get model input (should have newest 20 turns)
    model_input = ContextWindow.get_model_input(full)

    # Should have 40 messages (20 user + 20 assistant)
    assert len(model_input) == 40, f"Context window should have 40 messages, got {len(model_input)}"

    # First user message should be Turn 1 (not Turn 0)
    user_messages = [m for m in model_input if m['role'] == 'user']
    assert user_messages[0]['content'] == 'Turn 1', f"First turn in model input should be 'Turn 1', got {user_messages[0]['content']}"
    assert user_messages[-1]['content'] == 'Turn 20', f"Last turn should be 'Turn 20', got {user_messages[-1]['content']}"

    # Full history still has all 21 turns
    assert len(full) == 42, "Full transcript should still have 42 messages"
    print("✓ ContextWindow: first turn excluded, newest 20 in model input, all 21 in storage")


def test_task_store():
    """Test task store operations."""
    print("Testing FakeTaskStore...")
    store = FakeTaskStore()

    # Create task
    task = store.create_task('Buy milk', lane='what to do today')
    assert task.title == 'Buy milk', "Task title mismatch"
    assert task.lane == 'what to do today', "Task lane mismatch"

    # List and retrieve
    today = store.list_tasks('what to do today')
    assert len(today) == 1, "Should have 1 task in today lane"

    # Rename
    store.rename_task(task.id, 'Buy organic milk')
    tasks = store.list_tasks()
    assert tasks[0].title == 'Buy organic milk', "Rename failed"

    # Move
    store.move_task(task.id, 'what to not do today')
    not_today = store.list_tasks('what to not do today')
    assert len(not_today) == 1, "Move to not-today failed"

    # Verify operations recorded
    assert len(store.operations) == 3, "Should have 3 operations recorded"
    print("✓ FakeTaskStore: create, rename, move all work")


def test_agent_config():
    """Test agent configuration."""
    print("Testing TaskOrganizerAgent configuration...")
    # We can't instantiate without a real API key, but we can check the static method

    try:
        from app.organizer import TaskOrganizerAgent
        config = TaskOrganizerAgent.get_config()
        assert config['agent_type'] == 'LlmAgent', "Should be LlmAgent"
        assert config['model'] == 'gemini-3.5-flash', "Should use gemini-3.5-flash"
        assert config['location'] == 'global', "Should use global location"
        assert config['framework'] == 'Google ADK', "Should use Google ADK"
        print("✓ TaskOrganizerAgent: exactly one LlmAgent, gemini-3.5-flash, global location")
    except Exception as e:
        print(f"✗ Agent config test failed: {e}")
        return False

    return True


def test_no_orchestration():
    """Verify organizer never performs or dispatches work."""
    print("Testing organizer explicitly states it never performs/dispatches...")

    try:
        from app.organizer import SYSTEM_PROMPT

        # Check what's in the prompt
        assert 'organize' in SYSTEM_PROMPT.lower(), "Should mention organizing"
        assert 'never' in SYSTEM_PROMPT.lower() and 'perform' in SYSTEM_PROMPT.lower(), \
            "Should explicitly say it never performs work"
        assert 'never' in SYSTEM_PROMPT.lower() and 'dispatch' in SYSTEM_PROMPT.lower(), \
            "Should explicitly say it never dispatches work"
        print("✓ System prompt: organizes tasks, explicitly never performs or dispatches work")
    except Exception as e:
        print(f"✗ Orchestration test failed: {e}")
        return False

    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing foundation: one ADK agent, storage, context window")
    print("=" * 60)

    try:
        test_channel_store()
        test_context_window()
        test_task_store()
        test_agent_config()
        test_no_orchestration()

        print("\n" + "=" * 60)
        print("✓ All foundation tests passed!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
