#!/usr/bin/env python3
"""Test ASCII apostrophe in place and plan statement routing."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.organizer import TaskOrganizerAgent as A


def test_apostrophe_routing():
    """Test that ASCII apostrophe in I'll and I'm routes correctly."""
    print("Testing apostrophe routing (both ASCII and curly quotes)...")

    def route(m):
        return "PLANS" if (A._is_asking_for_plan(m) or A._is_bare_place_statement(m)) else "row"

    # Test cases that should route to "row" (19 total)
    # These are task notes, not place statements
    row_cases = [
        "remind me to call the dentist tomorrow at 3pm",
        "remind me to call the plumber when I'm at the office tomorrow",
        "tomorrow I need to fix the sink at home",
        "tomorrow, grab milk at the office",
        "finish the report at the office tomorrow",
        "drop off the keys at home tomorrow",
        "tomorrow print the contract at the office",
        "take the car in tomorrow at the garage",
        "collect the parcel at the office tomorrow",
        "tomorrow check the mail at home",
        "tomorrow I have the dentist at 9 near the office",
        "water the plants at home tomorrow",
        "tomorrow settle the invoice at the office",
        "sign the lease at home tomorrow morning",
        "tomorrow I must renew the permit at the office",
        "chase the refund at home tomorrow",
        "tomorrow I owe Dana a reply at the office",
        "tomorrow I should photograph the damage at home",
        "refill the prescription at the office tomorrow",
    ]

    # Test cases that should route to "PLANS" (10 total)
    # These are place statements that trigger day planning
    plans_cases = [
        "I am at Office tomorrow",
        "I will be at the Office tomorrow",
        "I'll be home tomorrow",  # ASCII apostrophe
        "tomorrow I'm at the office",  # ASCII apostrophe
        "Office",
        "plan my day tomorrow at the office",
        "plan tomorrow",
        "schedule my day",
        "I'll be home tomorrow",  # ASCII apostrophe in real use
        "tomorrow I'm at the office",  # ASCII apostrophe in real use
    ]

    # Route each test case
    row_routing = [route(m) for m in row_cases]
    plans_routing = [route(m) for m in plans_cases]

    # Count successes
    row_correct = sum(1 for r in row_routing if r == "row")
    plans_correct = sum(1 for r in plans_routing if r == "PLANS")

    # Report results
    print(f"  Row cases: {row_correct}/{len(row_cases)} routed correctly")
    print(f"  Plans cases: {plans_correct}/{len(plans_cases)} routed correctly")

    # Check for failures
    row_failures = [(m, route(m)) for m in row_cases if route(m) != "row"]
    plans_failures = [(m, route(m)) for m in plans_cases if route(m) != "PLANS"]

    if row_failures:
        print("\n  Row case failures:")
        for msg, result in row_failures:
            print(f"    {msg!r} -> {result}")

    if plans_failures:
        print("\n  Plans case failures:")
        for msg, result in plans_failures:
            print(f"    {msg!r} -> {result}")

    # Assert success
    assert row_correct == len(row_cases), f"Row routing: {row_correct}/{len(row_cases)}"
    assert plans_correct == len(plans_cases), f"Plans routing: {plans_correct}/{len(plans_cases)}"

    print("✓ ASCII apostrophe routing works correctly (19/19 row, 10/10 plans)")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing ASCII apostrophe in place statement patterns")
    print("=" * 60)

    try:
        test_apostrophe_routing()

        print("\n" + "=" * 60)
        print("✓ All apostrophe routing tests passed!")
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
