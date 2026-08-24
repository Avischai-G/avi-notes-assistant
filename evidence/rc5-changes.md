# RC5 changes

RC5 sits on `avi-notes-assistant-rc4`
(`23d43fa79c49a971905f4c2fbd7c8cf716a92189`). The first rc5 commit was
`5a3ac640db91a77af96cbe194e95f5cd00766be2`. That commit introduced two
regressions while fixing mixed create-and-plan replies, and it did not complete
the requested demo shot-list rewrite. All three issues were introduced and
corrected within rc5; rc1 through rc4 are unchanged.

## What actually shipped

### Reply composition regression — introduced and fixed in rc5

The first rc5 implementation called `_final_text` only after a create or update,
then returned raw `model_text` for ordinary chat. That bypassed both the
at-most-one-question guard and the `"Done."` fallback.

The corrected implementation always gets the non-plan reply from `_final_text`.
A plan replaces that reply only when the turn created or updated nothing. When a
turn both writes and plans, the write reply remains first, followed by one blank
line and the plan. Tests cover the four reply outcomes explicitly:

- task creation without a plan: the existing confirmation alone;
- a plan without a create or update: the plan alone;
- task creation plus a plan: confirmation, blank line, then plan;
- neither: guarded model text, including question truncation and empty fallback.

### Board-place instruction regression — introduced and fixed in rc5

The first rc5 implementation initialized the place hint with `Anywhere`, even
when board reads were disabled. It could therefore assert that Avi's board
contained only `Anywhere` without reading it. It also tied normal board reads to
whether a channel transcript already existed.

The corrected implementation emits no place sentence unless
`DayPlanner.recent_places()` actually read the task store. Normal chat channels
read current board values on their first turn as on later turns. Automation
channels retain the same exclusion, perform no board read, and receive no board
contents claim. The single chokepoint board-tool gate is unchanged.

### Demo shot list — completed in corrected rc5

The first rc5 commit changed one row to recommend retrying a model-decided shot;
it did not provide a usable recording script. `docs/SHOT-LIST.md` is now a
single-take, English 3:40 script with start times and durations, a problem/value
hook, spoken narration for every shot, continuous-take recovery lines, a live
`*.run.app/api/health` Cloud Run proof frame, a real marker-filtered Notion
mutation, architecture, publication checks, and explicit credential and private
task exclusions. It states throughout that the app organises and never executes.

The shot list was checked against the live official Devpost rules on
2026-08-24:
<https://allthingsagentichackathon.devpost.com/rules>.

## Failing-first evidence

With only the new regression tests applied to `5a3ac640`, before the organizer
fix, this command failed:

```sh
./.venv/bin/python -m pytest -q tests/test_routing_and_place_extraction.py
```

```text
FAILED tests/test_routing_and_place_extraction.py::test_plain_chat_reply_passes_through_one_question_guard
FAILED tests/test_routing_and_place_extraction.py::test_empty_plain_chat_reply_uses_done_fallback
FAILED tests/test_routing_and_place_extraction.py::test_first_turn_in_new_normal_channel_reads_real_board_places
FAILED tests/test_routing_and_place_extraction.py::test_automation_turn_neither_reads_nor_claims_board_places
4 failed, 22 passed, 2 warnings in 0.88s
```

After the organizer correction, the same focused file reported:

```text
26 passed, 2 warnings in 0.79s
```

## Required verification

Fresh shell, bare mode:

```sh
./.venv/bin/python -m pytest -q
```

```text
120 passed, 1 skipped, 3 warnings in 4.14s
```

Fresh shell, Vertex environment flag:

```sh
GOOGLE_GENAI_USE_VERTEXAI=true ./.venv/bin/python -m pytest -q
```

```text
120 passed, 1 skipped, 515 warnings in 4.15s
```

The suite uses offline scripted models and task stores; setting the environment
flag did not contact Vertex or Notion.

`npm run test:ui` is **UNVERIFIED** in this sandbox. No live browser-test server
was running, so the suite stopped before launching or checking Chromium:

```text
UI_BROWSER_SUITE_FATAL TypeError: fetch failed
    at node:internal/deps/undici/undici:16416:13
    at process.processTicksAndRejections (node:internal/process/task_queues:103:5)
    at async assertExpectedServer (file:///Users/avischaigrau/Documents/Agentonomy-Files/workspaces/ad76676a-7c78-4adc-9a3e-381b307fa7d6/tasks/47292aae/rc5/tests/ui_browser_suite.mjs:40:20)
    at async main (file:///Users/avischaigrau/Documents/Agentonomy-Files/workspaces/ad76676a-7c78-4adc-9a3e-381b307fa7d6/tasks/47292aae/rc5/tests/ui_browser_suite.mjs:362:3)
```

No Vertex or Notion call, board read/write, Google Cloud resource change, remote
push, publication, registration, or submission was attempted.
