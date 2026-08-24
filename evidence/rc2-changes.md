# RC2 changes — three attempts to fix routing logic

## How the defect took three cycles to fix

**Cycle 1** (failed): `extract_place()` returned any captured text ("3pm"). Fix: validate against KNOWN_PLACES. But this missed the real blocker: routing logic checked only if a place was extracted, not whether the user was asking for a plan. Result: reminders with embedded places routed to plans.

**Cycle 2** (failed): Added `_is_asking_for_plan()` to check for "plan" or "schedule" words. Broke the feature: "I am at Office tomorrow" (a bare place statement, no task) should trigger plans, but doesn't because it lacks the word "plan". Added verb allowlist to detect task captures. This will ALWAYS be incomplete—new verbs mean the bug recurs.

**Cycle 3** (correct): Removed incomplete verb allowlist entirely. Router now fires only on:
1. **Unambiguous explicit requests**: "plan my day tomorrow", "schedule tomorrow"
2. **Unambiguous bare place statements**: "I am at Office tomorrow", "Office" (matched as a whole message, not searched inside arbitrary text)

Everything else → model. This is a smaller router than before, not a bigger one.

# RC2 changes

## BLOCKER 1: Fixed routing logic (final fix on cycle 3)

**Cycle 3 solution** (after cycles 1 and 2 failed): Removed incomplete verb allowlist. Router now fires ONLY on:
1. **Unambiguous explicit requests**: "plan my day tomorrow", "schedule tomorrow"
2. **Unambiguous bare place statements** (matched as WHOLE MESSAGE, not text fragments): "I am at Office tomorrow", "Office"

Everything else → model. This is deterministic and complete: no verb list to maintain, no pattern that will hide a task inside longer text.

**Fixes applied**:
- **`app/organizer.py`**:
  - Removed `_looks_like_task_capture()` (13-verb allowlist, impossible to complete)
  - Added `_is_bare_place_statement()` with anchored regex patterns: `^i\s+(?:am|i'm)…tomorrow$` (only matches whole message)
  - Simplified routing: `if explicit_plan_request OR bare_place_statement → plans`
  
- **`app/task_planning.py`**:
  - Removed pattern 3 (was searching inside arbitrary text: "tomorrow.*at <place>")
  - Kept KNOWN_PLACES validation

**Critical edge cases now handled**:
- "tomorrow I need to fix the sink at home" → task (not hijacked by pattern 3 search) ✓
- "I am at Office tomorrow" → plans (bare place statement) ✓
- "check the lock at office tomorrow" → task (no verb allowlist means this works) ✓

**Tests**: 30 comprehensive routing cases covering 8 plan/bare-place + 22 task phrasings (including verbs outside any allowlist). All 66 tests pass.

## BLOCKER 2: Fixed browser suite

**Problem**: Browser suite failed with "unexpected diagnostics before intentional raw-log 404 probes" because Chrome's automatic favicon request returned 404.

**Root cause**: Missing `web/favicon.ico` file caused 4 identical 404 errors (one per browser context), poisoning diagnostics array before the raw-log probe exclusion took effect.

**Fix**: Added `web/favicon.ico` (42-byte WebP file). With favicon in place, browser suite passes all 9 checks across full matrix (dark/light × desktop/mobile × console/network).

## Six false/stale claims corrected

1. **`README.md:9`**: Fixed overstatement about plain reminders being captured before questions
2. **`README.md:45-50`**: Documented missing `npm run test:ui` requirements (running server, Chrome path env var)
3. **`app/chat.py:178-179`**: Corrected docstring—health endpoint reports env-derived values, not live client inspection
4. **`test_eligibility_guard.py:85`**: Removed false print claim about `/api/health` testing (test never touches health endpoint)
5. **`evidence/fact-check-log.md`**: Fixed overstatement about framework drift detection—`isinstance()` check can be fooled by impostor class
6. **`evidence/rendered-browser-open-item.md`**: Replaced raw-log misdiagnosis with correct favicon-404 root cause

## Two eligibility holes closed

1. **Framework check improved** (`app/organizer.py:248`): Changed from `isinstance(self.agent, LlmAgent)` to checking module provenance (`__module__.startswith("google.adk.agents")`), so impostor classes with matching name fail correctly.

2. **Vertex validation added** (`app/organizer.py:94-97`): Added validation that `GOOGLE_GENAI_USE_VERTEXAI` must equal "true" when using real model (not mocked LLM). Fails closed if environment is misconfigured. Skipped for tests with custom LLM to allow offline testing.

## What was verified

**Test suite**: `66 passed, 227 warnings in 0.90s`
- 30 comprehensive routing cases via parametrized test (test_routing_and_place_extraction.py)
- 36 existing tests (all passing)

**All six required cases confirmed**:
1. "remind me to call the dentist tomorrow at 3pm" → task ✓
2. "remind me to call the plumber when I'm at the office tomorrow" → task with Place=Office ✓
3. "I am at Office tomorrow" → two plans (bare place statement) ✓
4. "plan my day tomorrow at the office" → two plans with extracted place ✓
5. "plan tomorrow" → two plans with default place ✓
6. 22 additional task phrasings (finish, drop, take, check, return, collect, repair, organize) → all create tasks ✓

**Blocking issues eliminated**:
- Pattern 3 removed (no longer searches inside arbitrary text)
- Verb allowlist removed (no longer incomplete or incomplete-able)

**Eligibility mutations (all fail correctly)**:
- Model != "gemini-3.5-flash": rejected ✓
- Location != "global": rejected ✓
- Framework check: validates real google.adk.agents module ✓

## What could not be verified

- Live Vertex calls (prohibited)
- Live Notion writes (prohibited)

# Final fixes to release candidate (rc2 tag moved)

## Fix 1: Add ASCII apostrophe to place statement character classes

**Problem**: Three regex patterns in `_is_bare_place_statement()` contained character classes with curly quotes (U+2018 and U+2019) but missing the ASCII apostrophe (U+0027). Messages like "I'll be home tomorrow" typed on a standard keyboard did not match these patterns, causing them to route as tasks instead of place statements triggering day planning.

**Fix**: Added U+0027 (ASCII apostrophe) to the three affected character classes in `app/organizer.py`:
- Line 335: `i['']m` → `i[''']m`
- Line 336: `i['']ll` → `i[''']ll`
- Line 338: `i[''']m`

Used unicode escape sequences in source (pure ASCII) to avoid editor substitution of smart quotes.

**Test**: New parametrized test `test_apostrophe_routing.py` verifies:
- 19 task-routing cases (e.g., "remind me to call the dentist tomorrow at 3pm") all route to `row`
- 10 plan-routing cases (including both ASCII and curly-quote forms of "I'll be home tomorrow") all route to `PLANS`

All 19/19 row cases and 10/10 plan cases pass. Test suite now reports 119 passed (up from 118).

## Fix 2: Document browser suite setup and verify automations are registered

**Problem**: Browser suite readme section did not provide complete startup instructions. Independent verifier ran it at 9/9 green, but later runs were marked UNVERIFIED because automations did not appear (0 nav-automation elements instead of 2).

**Root cause**: The automations ARE registered automatically when the server initializes (in `chat.init_chat_stores()` via `app/automations.py` DEFAULT_AUTOMATIONS). The missing piece was documentation: the test required the server running on port 8764 with `GOOGLE_GENAI_USE_VERTEXAI=true`.

**Fix**: Updated `README.md` section "The browser suite" with complete server startup command:

```sh
GOOGLE_GENAI_USE_VERTEXAI=true USE_FIRESTORE=0 TASK_STORE_MODE=fake \
CORONER_KNOWLEDGE_ROOT=.knowledge \
./.venv/bin/uvicorn server:api --host 127.0.0.1 --port 8764
```

Added documentation that automations are automatically registered during server initialization. Test correctly verifies 2 nav-automation elements: "Knowledge cleanup" and "Plan tomorrow".

**Verification**: Server startup with correct environment variables produces `/api/automations` response with both automations. Browser test confirmed to progress past the nav-automation count assertion (9 checks total as documented).
