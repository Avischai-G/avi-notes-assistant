# Release-candidate evidence — start here

## Current conclusion

The five card outputs are integrated in this workspace-local clone. The merged
offline suite passes with all final safeguards: `114 passed, 1
skipped`. Live Notion isolation and exact five-operation
discovery passed. Explicitly selecting the existing Firestore Native `coroner`
database resolved startup without a resource change or fallback.

The approved story is complete across the observed task phase and authorized
continuation. Task capture, vague-answer handling, two-plan ordering, Plan A's
When-only writes, non-execution language, two Knowledge cleanup runs in one
persistent channel, day/week/month Learning movement, live raw-log 404s, and
full service-reload persistence passed. A single shared channel gate now refuses
all five agent tools, including tomorrow planning, in automation or unknown channels without touching Notion.
Mandatory cleanup proved `remaining_marker_rows=0`.

Rendered-browser QA passes 9/9 at rc4: the independent verifier and the Main
Orchestrator each ran the unchanged suite against this tag and both observed
`UI_BROWSER_SUITE pass=9 fail=0 total=9`. The suite drives a mocked model, so
this proves browser behavior and wiring only, not natural-language model
routing.

## Decision criteria

Green requires all seven live-story steps, Notion isolation `PASS`, real
model/location/framework drift assertions, secret scans of worktree and reachable
history, a clean-checkout test, and a local release tag. All live criteria now
pass. The merged desktop/mobile dark/light browser matrix passed at rc3 and has
an attributed 9/9 rc4 working-tree run; first-party rc4 rendering remains
explicitly `UNVERIFIED` here.

## Fixed boundaries

- Existing Notion database; frozen six-property schema.
- Exact five-operation MCP allowlist and row-aware isolation: one configured
  data source, only pages parented to it, and `has_more=false`.
- One Google ADK `LlmAgent`, `gemini-3.5-flash`, `global`.
- Explicit Firestore database selection via `FIRESTORE_DATABASE`, default
  `coroner`; connection errors fail closed.
- 123-word base prompt; the model distinguishes tasks, chat, and planning; no more than one question per item.
- Nightly planning at 21:00 `Asia/Jerusalem`; two picks; pick writes only `When`.
- One shared channel gate refuses every board and planning tool in automation and unknown
  channels; refusals are model-readable and never fall back to local storage.
- The pre-existing board row is excluded from all model, planner, cleanup, and test counts.
- No deployment, remote push, publication, recording, registration, submission, or scope cut.

## Release identity

The rc4 source/evidence tree is frozen by local tag
`avi-notes-assistant-rc4`; the release check requires that tag and `HEAD` resolve
to the same commit. No remote or outward action is part of this release. See
`rc4-changes.md`, `final-release-verification.md`, and
`live-acceptance-2026-08-24.md`.
