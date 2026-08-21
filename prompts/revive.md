---
description: Writes the resume plan - what is still salvageable and how to restart it
---

# Revival

## Cause of death as certified

{certificate}

## Your job

Write the resume plan. This run's remaining work is not automatically lost —
decide what can still be salvaged and how to restart it.

- 'revivable' is false only if the run genuinely completed, was aborted on
  purpose by a human, or its request no longer makes sense. Being stuck is not
  a reason to declare it unrevivable.
- 'skip' lists the step ids already banked so the restart does not redo them.
- 'unblock' is the single condition that must hold before restarting. If the
  run died waiting on a human, do NOT write "the user must answer" — that is
  what already failed. Write the assumption the orchestrator should proceed
  under instead, chosen so that being wrong is cheap and visible.
- 'restart_prompt' is handed verbatim to the orchestrator. Never assert
  anything that has not happened — in particular never claim the human
  answered. State the assumption openly, instruct the orchestrator to proceed
  on it and to flag it in its output, and carry forward what is already done.
