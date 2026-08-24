# RC2 changes

## BLOCKER 1: Fixed routing logic

**Problem**: Reminders containing "tomorrow at X" where X is an unknown place (like "3pm") were being routed to day-planning instead of task creation, causing 7 of 10 realistic reminders to be silently discarded.

**Fix**: Modified `app/task_planning.py:extract_place()` to only return places that match known places from recent tasks. Unknown places like times are no longer returned, preventing false day-plan triggers for reminders.

**Test coverage**: Added comprehensive test suite `tests/test_routing_and_place_extraction.py` with:
- Five specific behaviors from BLOCKER 1 (reminder with time, reminder with place, plan request with place, plan without place, anywhere default)
- Twelve realistic reminder phrasings covering various combinations of times, places, and neither

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

- All 42 tests pass with proper environment
- New routing tests verify all five behaviors and twelve realistic phrasings  
- Fixed `extract_place()` logic confirmed via direct testing
- Framework check verified to reject impostor LlmAgent
- Vertex validation confirmed to require proper environment
- Browser suite still passes 9/9 with favicon added
- No secrets in worktree or git history

## What could not be verified

- Browser suite on this executor's Chrome (SIGABRT was environment limit, not product fault)
- Live Notion writes (instruction prohibited)
- Live Vertex calls (instruction prohibited)
