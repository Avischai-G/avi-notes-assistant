# RC4 - model-routed task and day planning

Release identity: local tag `avi-notes-assistant-rc4`. At freeze,
`git rev-list -n1 avi-notes-assistant-rc4` and `git rev-parse HEAD` must resolve
to the same commit. This symbolic citation avoids claiming an ancestor as the
tagged commit.

## What was deleted

- The pre-model `_is_asking_for_plan` and `_is_bare_place_statement` regex
  router, its punctuation normalization, and every caller.
- `DayPlanner.extract_place`, its regex battery, `_is_known_place`, and the
  hardcoded `KNOWN_PLACES` set.
- Two tests of the deleted predicates. Their required cases now run through
  `TaskOrganizerAgent.chat()` with a scripted `BaseLlm`.

Core source diff at the measured working tree:

```text
36  76  app/organizer.py
10  49  app/task_planning.py
```

## What replaced it

The same single Google ADK `LlmAgent` now receives `plan_tomorrow` beside the
four TaskStore tools. The existing `_gate_board_tool` list comprehension wraps
all five, so automation and unknown channels refuse planning through the same
chokepoint as row operations. The tool accepts an optional Place and returns
the existing `DayPlanner.build()` sweep. The visible response and two pick
controls come from that sweep.

`DayPlanner.build()` canonicalizes a supplied place against `recent_places()`
plus `Anywhere`. No product source contains Home, Office, Out, Studio, or any
other user place literal. `build()` and `pick()` retain the two orderings,
eight-hour budget, Jerusalem times, place filtering, and When-only writes.

The eligibility exemption now covers only `TASK_STORE_MODE=fake` and pytest.
`USE_FIRESTORE=0` no longer says anything about the model backend. Production
`app/chat.py` still constructs `TaskOrganizerAgent` without `llm=`.

## Prompt

Measured: `PROMPT_WORDS=123`.

```text
You are Avi's assistant. He talks naturally; you organize and keep his notes and tasks in Notion, say what you wrote, and never do the task itself. A task is something he wants to remember or do; questions and conversation are not tasks. For a day plan or his tomorrow location, call plan_tomorrow and pass any place he names.

Capture tasks first. Ask at most one useful question per item, usually When. If he answers, update the item. If he is vague or moves on, keep the default, state it once, and never ask again.

Defaults: Status=Not started; Place=Anywhere; Minutes=30; Notes=his words; When=explicit time, today for today/now/tonight/urgent, tomorrow for a plain reminder, empty for a someday idea. Always state the applied defaults briefly.
```

## Measured behavior

All routing cases use a mocked ADK model; no Vertex, Notion, or external network
call occurs. The tests parameterize seven task phrasings, nine plan/place
phrasings with punctuation and both apostrophe forms, the exact shot-list
Office sentence, board-only `Studio`, multi-word `Coffee Shop`, and a plain
question. The scripted model discards each message, so these parameters establish
repeated plumbing coverage for the fixed tool choices, not model routing behavior.
Source messages use Unicode escapes; `cat -v` over the core source and
behavior files produced `CAT_V_ASCII=PASS`.

The preserved tests also cover the vague default without a model call or
re-ask, at most one question, different plan orderings, place filtering, the
eight-hour cap, and `pick()` changing only `When`.

Required pytest commands, measured on the rc4 working tree:

```text
114 passed, 1 skipped, 3 warnings in 3.98s
114 passed, 1 skipped, 451 warnings in 3.98s
```

Eligibility construction probe:

```text
fake store, Vertex unset: CONSTRUCTED (exit=0)
notion store + USE_FIRESTORE=0, Vertex unset: REFUSED (exit=3)
notion store + USE_FIRESTORE=0, Vertex true: CONSTRUCTED (exit=0)
Cloud Run shape, Vertex unset: REFUSED (exit=3)
```

Static boundary probe:

```text
MCP_ALLOWLIST=create_page,set_page_title,set_page_property,query_database,archive_page
LLMAGENT_CONSTRUCTORS=1
RUNNER_CONSTRUCTORS=1
FROZEN_BOUNDARY_DIFF=NONE
STATIC_CHECKS=PASS
```

Secret scan of the pre-commit working tree and reachable history:

```text
SECRET_SCAN=PASS worktree_files=88 reachable_history_bytes=3457635 exact_sensitive_values=5 generic_patterns=4
```

## Rendered browser attribution

Rendered QA is `UNVERIFIED` from this executor's sandbox. Chromium requires
Mach bootstrap registration, denied here with error 1100 before any page opens.
The Main Orchestrator ran the unchanged suite outside this sandbox at local tag
`avi-notes-assistant-rc4`. They confirmed the tag and `HEAD` matched, the
worktree and remote list were empty, `/api/health` reported the expected rc4
fixture, npm exited 0, and the worktree stayed clean. They supplied this raw
result:

```text
UI_BROWSER_SUITE pass=9 fail=0 total=9
PASS task-dark-desktop
PASS learning-dark-desktop
PASS task-light-desktop
PASS learning-light-desktop
PASS task-dark-mobile
PASS learning-dark-mobile
PASS task-light-mobile
PASS learning-light-mobile
PASS browser-console-and-network - no console errors, page errors, or failed requests
```

A stale orphaned static server was observed occupying port 8764 and returning
HTML 404 at `/api/health`. The suite now checks the health content type, expected
build revision, model, location, framework, and local-store mode before Chrome.
The negative probe failed immediately, before browser launch:

```text
UI_BROWSER_SUITE_FATAL Error: http://127.0.0.1:8877 is not the expected app: GET /api/health returned 404 (text/html;charset=utf-8). Free its port and start the documented browser-test server.
```

## UNVERIFIED

- First-party rendered rc4 QA from this executor; see the attributed 9/9 run.
- Live Vertex and live Notion. Prohibited and not attempted.
- Cloud Run deployment, Cloud Storage mounting, scheduler operation, and any
  cloud-resource behavior. Nothing was deployed or changed.
- Natural-language behavior of the live Gemini model outside the brief prompt;
  integration behavior is proved with a mocked model only.
- Publication, push, registration, recording, and submission. None occurred.
