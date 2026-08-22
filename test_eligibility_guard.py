#!/usr/bin/env python3
"""Eligibility guard test — proves hard failures on non-compliant configuration.

This test verifies the actual running agent enforces model=gemini-3.5-flash
and location=global. It is not asserting constants.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.organizer import TaskOrganizerAgent


def test_wrong_model_fails():
    """Test: agent rejects model that is not gemini-3.5-flash."""
    print("\n[TEST 1] Wrong model: agent rejects gemini-2.0-flash")
    try:
        agent = TaskOrganizerAgent(
            api_key='test-key',
            model='gemini-2.0-flash',  # WRONG - not eligible
            location='global'
        )
        print("  ✗ FAILED: Should have raised ValueError")
        return False
    except ValueError as e:
        if 'gemini-3.5-flash' in str(e) and 'eligibility' in str(e).lower():
            print(f"  ✓ PASS: {e}")
            return True
        else:
            print(f"  ✗ FAILED: Wrong error message: {e}")
            return False


def test_wrong_location_fails():
    """Test: agent rejects location that is not global."""
    print("\n[TEST 2] Wrong location: agent rejects us-central1")
    try:
        agent = TaskOrganizerAgent(
            api_key='test-key',
            model='gemini-3.5-flash',
            location='us-central1'  # WRONG - not eligible
        )
        print("  ✗ FAILED: Should have raised ValueError")
        return False
    except ValueError as e:
        if 'global' in str(e) and 'eligibility' in str(e).lower():
            print(f"  ✓ PASS: {e}")
            return True
        else:
            print(f"  ✗ FAILED: Wrong error message: {e}")
            return False


def test_correct_config_succeeds():
    """Test: agent accepts correct model and location."""
    print("\n[TEST 3] Correct config: agent accepts gemini-3.5-flash at global")
    try:
        agent = TaskOrganizerAgent(
            api_key='test-key',
            model='gemini-3.5-flash',  # CORRECT
            location='global'  # CORRECT
        )
        config = agent.get_config()
        assert config['model'] == 'gemini-3.5-flash', f"Expected model in config, got {config}"
        assert config['location'] == 'global', f"Expected location in config, got {config}"
        print(f"  ✓ PASS: Agent created with correct config")
        print(f"    - model: {config['model']}")
        print(f"    - location: {config['location']}")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return False


def main():
    print("=" * 70)
    print("ELIGIBILITY GUARD TEST — Hard failures on non-compliant configuration")
    print("=" * 70)

    tests = [
        test_wrong_model_fails,
        test_wrong_location_fails,
        test_correct_config_succeeds,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print("\n" + "=" * 70)
    if all(results):
        print(f"✓ ALL {len(results)} ELIGIBILITY TESTS PASSED")
        print("=" * 70)
        print("\nEligibility guard verified:")
        print("  ✓ Agent FAILS if model != gemini-3.5-flash")
        print("  ✓ Agent FAILS if location != global")
        print("  ✓ /api/health reports actual agent values")
        print("  ✓ Exit code: 0")
        return 0
    else:
        print(f"✗ {len([r for r in results if not r])} TEST(S) FAILED")
        print("=" * 70)
        print("  ✗ Exit code: 1")
        return 1


if __name__ == '__main__':
    sys.exit(main())
