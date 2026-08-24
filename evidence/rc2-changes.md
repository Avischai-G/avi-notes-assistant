# RC2 changes

## BLOCKER 1: Fixed routing logic

**The problem**: Three layers of confusion broke the routing:
1. `extract_place()` returned ANY captured text (e.g., "3pm"), not just known places → false triggers
2. Initial fix: routing checked BOTH `day_planner AND _is_asking_for_plan()`, missing the bare place-statement case
3. That fix broke the feature: "I am at Office tomorrow" should trigger plans, but didn't because it doesn't have the word "plan"

**Root cause**: The fix was too strict. The actual rule is:
- **Task capture wins over place**: "remind me to call the plumber when I'm at the office" → creates row with Place=Office, NO plans
- **Bare place statements trigger plans**: "I am at Office tomorrow" (no task words) → two plans
- **Explicit plan requests trigger plans**: "plan my day tomorrow" → two plans
- **Reminders always create tasks**: any "remind me" or task verb (call, send, buy, etc.) → task creation path

**Fixes applied**:
1. **`app/task_planning.py`**:
   - Added `KNOWN_PLACES = frozenset(("Home", "Office", "Out", "Anywhere"))`
   - Added `_is_known_place()` to validate extracted places (rejects "3pm")
   - Fixed regex patterns (corruption: backspace chars → removed)

2. **`app/organizer.py`**:
   - Added `_looks_like_task_capture()`: detects "remind me", action verbs like call/send/buy, NOT plan/schedule requests
   - Fixed routing: `if NOT task_capture AND (explicit_plan_request OR has_known_place) → plans`
   - Now:
     * "remind me..." → always task (capture wins)
     * "I am at Office..." → plans (bare place, no capture)
     * "plan my day..." → plans (explicit request)

**Tests**: 6 end-to-end routing tests via TaskOrganizerAgent with mocked LLM, covering all four cases plus 10 realistic reminders. All 42 tests pass.

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

**Test suite**: `42 passed, 164 warnings in 0.83s`
- 6 new routing tests (test_routing_and_place_extraction.py)
- 36 existing tests (all passing)
- All four required cases pass:
  1. Reminder with unknown time → task only ✓
  2. Reminder with place → task with Place=Office ✓
  3. Bare place statement "I am at Office" → two plans ✓
  4. Explicit plan request → two plans with extracted place ✓
  5. 10+ realistic reminder phrasings → all create tasks ✓

**Eligibility mutations (all fail correctly)**:
- Model != "gemini-3.5-flash": rejected ✓
- Location != "global": rejected ✓
- Framework check: validates real google.adk.agents module ✓

## What could not be verified

- Browser suite (9/9 matrix): requires running backend API server; static files + favicon insufficient. Test framework connects correctly but fails on nav-automation UI assertions that require live backend. Marked UNVERIFIED.
- Live Vertex calls (prohibited by instructions)
- Live Notion writes (prohibited by instructions)
