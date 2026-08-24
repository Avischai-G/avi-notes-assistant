#!/usr/bin/env python3
"""Eligibility guard test — proves hard failures on non-compliant configuration.

This test verifies the actual running agent enforces model=gemini-3.5-flash
and location=global. It is not asserting constants.
"""

import sys
import os
from pathlib import Path
import subprocess
import pytest
sys.path.insert(0, os.path.dirname(__file__))

from app.organizer import TaskOrganizerAgent


ROOT = Path(__file__).resolve().parent
CONSTRUCTION_PROBE = """\
from app.organizer import TaskOrganizerAgent
try:
    TaskOrganizerAgent()
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}")
    raise SystemExit(3)
print("CONSTRUCTED")
"""


def _probe_construction(extra_env):
    return subprocess.run(
        [sys.executable, "-c", CONSTRUCTION_PROBE],
        cwd=ROOT,
        env=extra_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def test_wrong_model_fails():
    """Test: agent rejects model that is not gemini-3.5-flash."""
    print("\n[TEST 1] Wrong model: agent rejects gemini-2.0-flash")
    with pytest.raises(ValueError, match="gemini-3.5-flash"):
        TaskOrganizerAgent(
            api_key='test-key',
            model='gemini-2.0-flash',  # WRONG - not eligible
            location='global'
        )
    print("  ✓ PASS: wrong model rejected")


def test_wrong_location_fails():
    """Test: agent rejects location that is not global."""
    print("\n[TEST 2] Wrong location: agent rejects us-central1")
    with pytest.raises(ValueError, match="global"):
        TaskOrganizerAgent(
            api_key='test-key',
            model='gemini-3.5-flash',
            location='us-central1'  # WRONG - not eligible
        )
    print("  ✓ PASS: wrong location rejected")


def test_correct_config_succeeds():
    """Test: agent accepts correct model and location."""
    print("\n[TEST 3] Correct config: agent accepts gemini-3.5-flash at global")
    agent = TaskOrganizerAgent(
        api_key='test-key',
        model='gemini-3.5-flash',  # CORRECT
        location='global'  # CORRECT
    )
    config = agent.get_config()
    assert config['model'] == 'gemini-3.5-flash', f"Expected model in config, got {config}"
    assert config['location'] == 'global', f"Expected location in config, got {config}"
    print("  ✓ PASS: Agent created with correct config")
    print(f"    - model: {config['model']}")
    print(f"    - location: {config['location']}")


@pytest.mark.parametrize(
    "name,env,constructs",
    [
        ("fake_without_vertex", {"TASK_STORE_MODE": "fake"}, True),
        (
            "notion_without_vertex",
            {"TASK_STORE_MODE": "notion", "USE_FIRESTORE": "0"},
            False,
        ),
        (
            "notion_with_vertex",
            {
                "TASK_STORE_MODE": "notion",
                "USE_FIRESTORE": "0",
                "GOOGLE_GENAI_USE_VERTEXAI": "true",
            },
            True,
        ),
        (
            "cloud_run_without_vertex",
            {"TASK_STORE_MODE": "notion", "K_SERVICE": "avi-notes"},
            False,
        ),
    ],
)
def test_vertex_eligibility_combinations(name, env, constructs):
    result = _probe_construction(env)

    if constructs:
        assert result.returncode == 0, f"{name}: {result.stdout}"
        assert result.stdout.strip() == "CONSTRUCTED"
    else:
        assert result.returncode == 3, f"{name}: {result.stdout}"
        assert "GOOGLE_GENAI_USE_VERTEXAI must be set to 'true'" in result.stdout


def test_production_chat_never_injects_an_llm_override():
    source = (ROOT / "app" / "chat.py").read_text(encoding="utf-8")
    assert "llm=" not in source


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
            test()
            results.append(True)
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
        print("  ✓ Exit code: 0")
        return 0
    else:
        print(f"✗ {len([r for r in results if not r])} TEST(S) FAILED")
        print("=" * 70)
        print("  ✗ Exit code: 1")
        return 1


if __name__ == '__main__':
    sys.exit(main())
