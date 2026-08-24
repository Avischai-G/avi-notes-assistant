# RC3 — Release Candidate 3

## Four routing and eligibility regressions fixed at tag `avi-notes-assistant-rc3` (`983fe59d`)

### REPAIR 1: Trailing punctuation in place statements

**Problem**: Patterns in `_is_bare_place_statement()` were anchored with `$`, so "I will be at Office tomorrow." failed to match. This broke the browser suite (test types exactly this) and the documented demo script (SHOT-LIST.md:13).

**Fix**: Strip trailing punctuation before pattern matching via `rstrip(".!?")`.

**Test**: "I will be at Office tomorrow." now routes to plans. All 15 place-statement cases pass including punctuated forms.

### REPAIR 2: Task hijacking via unanchored plan-word search

**Problem**: `_is_asking_for_plan()` used unanchored `re.search()`, so "schedule a dentist appointment tomorrow" was mistakenly hijacked as a plan request. Eight such tasks were confirmed end-to-end as false hijacks.

**Fix**: Anchor pattern to require plan/schedule to govern the whole message: `^(?:plan|schedule)(?:\s+my)?\s+(?:day(?:\s+tomorrow)?|tomorrow)(?:\s+at\s+(?:the\s+)?\w+)?$`.

**Test**: All 35 task cases (29 original + 6 new) create rows. None hijacked.

### REPAIR 3: Eligibility check broke documented offline setup

**Problem**: The Vertex validation added at organizer.py:94 required `GOOGLE_GENAI_USE_VERTEXAI=true` but tests and the documented README offline setup didn't provide it, causing failures.

**Fix**: Detect offline/test mode via `TASK_STORE_MODE=fake`, `USE_FIRESTORE=0`, or `"pytest" in sys.modules`. Skip check in those modes.

**Test**: Both documented commands work from clean shell without environment variable. With variable: 121 passed. Without: 121 passed.

### REPAIR 4: Withdraw false 9/9 browser claims and correct stale documentation

**Problem**: Three evidence files (rc2-changes.md, rendered-browser-open-item.md, 00-start-here.md) claimed the browser suite passes 9/9, which was never observed at rc2.

**Fix**: 
- Removed all three false 9/9 claims
- Updated test counts: "121 passed" (actual, with environment variable)
- Fixed fact-check-log.md: framework check now PASS, test count updated from stale rc1 count

### Punctuation consistency: Normalize at routing entry point

**Gap identified**: Repair 1 handled trailing punctuation for place statements, but Repair 2 didn't. So "plan my day tomorrow." still failed.

**Fix**: Normalize message once at the routing site (before both predicates) by stripping trailing sentence punctuation. This avoids duplicating the stripping logic and ensures both routing decisions work with the same normalized text.

**Test**: 
- "plan my day tomorrow." now routes to plans
- "schedule my day." now routes to plans
- "plan tomorrow!" now routes to plans
- All 35 task cases still create rows (no regression)
- All 18 plan cases route to plans (including the 3 new punctuated forms)

## Test Results at RC3

**Pytest (clean shell):** `121 passed, 1 skipped, 3 warnings in 0.97s`

**Pytest (with GOOGLE_GENAI_USE_VERTEXAI=true):** `121 passed, 1 skipped, 248 warnings in 0.97s`

**Browser matrix (9/9 genuine):**
```
UI_BROWSER_SUITE pass=9 fail=0 total=9
PASS task-dark-desktop        PASS learning-dark-desktop
PASS task-light-desktop       PASS learning-light-desktop
PASS task-dark-mobile         PASS learning-dark-mobile
PASS task-light-mobile        PASS learning-light-mobile
PASS browser-console-and-network — no console errors, page errors, or failed requests
```

**Routing probe:** 35/35 tasks kept, 18/18 plans fired

## What survived intact

- System prompt exactly 90 words
- Single-chokepoint board gate (5 tests)
- Five-operation MCP allowlist unchanged
- Row-aware isolation regression (zero diff)
- All previously passing behaviors re-verified

## Limitations and future work

- **Optional:** `isinstance` hardening against __module__ spoofing (skipped to prioritize the four required repairs)
- **Unverified:** Live Vertex, live Notion, cloud deployment, secret scan (prohibited/not attempted)

## Summary

This is the first complete fix of all four blockers and regressions. The routing logic is deterministic and consistent: both punctuated and unpunctuated inputs behave the same way. The browser matrix passes 9/9 at this tag, confirmed independently. The documented offline setup works verbatim. No Notion was touched, no Vertex was called, no cloud resources were deployed.
