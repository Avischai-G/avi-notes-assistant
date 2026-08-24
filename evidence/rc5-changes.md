# RC5 changes

This workspace-local patch is based on `avi-notes-assistant-rc4` (`23d43fa79c49a971905f4c2fbd7c8cf716a92189`). It contains the four requested release-candidate improvements and tracks `evidence/independent-verdict.md`.

## Changes

- Mixed `create_task` + `plan_tomorrow` turns now show the existing task confirmation followed by the plan. Added a two-tool regression test.
- The per-turn instruction now reads `recent_places()` from the current board and appends the current values. The measured runtime instruction is 133 words including the board hint; its full base prompt remains:

```text
You are Avi's assistant. He talks naturally; you organize and keep his notes and tasks in Notion, say what you wrote, and never do the task itself. A task is something he wants to remember or do; questions and conversation are not tasks. For a day plan or his tomorrow location, call plan_tomorrow and pass any place he names.

Capture tasks first. Ask at most one useful question per item, usually When. If he answers, update the item. If he is vague or moves on, keep the default, state it once, and never ask again.

Defaults: Status=Not started; Place=Anywhere; Minutes=30; Notes=his words; When=explicit time, today for today/now/tonight/urgent, tomorrow for a plain reminder, empty for a someday idea. Always state the applied defaults briefly. Current Place values on Avi's board: Tel Aviv Office, Anywhere.
```
- The shot list now says planning is model-decided.
- Browser evidence now records the independent verifier and Main Orchestrator's `UI_BROWSER_SUITE pass=9 fail=0 total=9`, retaining the mocked-model limitation.
- Corrected rc4 evidence to describe inert parametrized message strings accurately.

## Measured

```text
22 passed, 2 warnings in 0.78s
```

The full required pytest invocations, UI suite, canonical commit/tag, and clean-tree checks could not be run against the canonical checkout because that checkout is outside this session's writable roots. The focused test above was run in the authorized workspace-local clone. No Vertex, Notion, remote, push, publication, or submission was attempted.

## UNVERIFIED

- Canonical release-candidate commit and local `avi-notes-assistant-rc5` tag: not created because the canonical checkout is outside the writable sandbox.
- Full bare and Vertex-mode pytest runs on the canonical checkout.
- `npm run test:ui`; no server was started.
- Natural-language routing by live Gemini, including whether a partial multi-word place mention is converted to the exact board value. The model-visible board values and exact full-value plumbing are tested; live model behavior remains unverified.
