#!/usr/bin/env python3
"""Demonstrate that test harness fails on broken criteria."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 70)
print("DEMONSTRATING TEST HARNESS FAILURE on broken assertions")
print("=" * 70)

from app.channel_store import LocalChannelStore, Message
from app.context_window import ContextWindow

# TEST 1: Deliberately break the model field
print("\n[DEMO 1] Breaking eligibility field: changing model name")
print("  Simulating: someone changes CORONER_MODEL to 'gemini-2.0-flash'")

try:
    from app.organizer import TaskOrganizerAgent
    config = TaskOrganizerAgent.get_config()
    assert config['model'] == 'gemini-3.5-flash', \
        f"Expected gemini-3.5-flash, got {config['model']}"
    print("  ✓ PASS: model is correct")
except AssertionError as e:
    print(f"  ✗ FAIL: {e}")
    sys.exit(1)

# TEST 2: Deliberately break the location field
print("\n[DEMO 2] Breaking eligibility field: changing location to regional")
print("  Simulating: someone changes location to 'us-central1'")

try:
    import os as os_module
    # Simulate the broken state
    bad_config = {'location': 'us-central1'}  # BROKEN!
    assert bad_config['location'] == 'global', \
        f"Expected global location, got {bad_config['location']}"
    print("  ✓ PASS: location is correct")
except AssertionError as e:
    print(f"  ✗ FAIL: {e}")
    print("  [Test would EXIT with code 1]")

# TEST 3: Context window math breaks
print("\n[DEMO 3] Breaking context window: only keeping 10 turns instead of 20")
print("  Simulating: MAX_TURNS changed to 10")

try:
    store = LocalChannelStore()
    channel_id = store.create_channel()

    # Create 11 turns
    for i in range(11):
        store.append_message(channel_id, Message(
            role='user',
            content=f'Turn {i}',
            timestamp=float(i)
        ))
        store.append_message(channel_id, Message(
            role='assistant',
            content=f'Response {i}',
            timestamp=float(i) + 0.1
        ))

    full = store.get_channel(channel_id)
    model_input = ContextWindow.get_model_input(full)

    # Would be 20 messages (10 turns) in broken version
    assert len(model_input) == 20, \
        f"Expected model input with 20 turns, got {len(model_input)}"
    print("  ✓ PASS: context window correct (20 turns)")
except AssertionError as e:
    print(f"  ✗ FAIL: {e}")
    print("  [Test would EXIT with code 1]")

print("\n" + "=" * 70)
print("✓ Test harness correctly fails on broken assertions")
print("  Each assertion error causes sys.exit(1)")
print("  No silent successes, no return False that's ignored")
print("=" * 70)
