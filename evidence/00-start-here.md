# Release-candidate evidence — start here

## Current conclusion

The five card outputs are integrated in this workspace-local clone. The merged
offline suite passes with all final safeguards: `88 passed, 1
skipped`. Live Notion isolation and exact five-operation
discovery passed. Explicitly selecting the existing Firestore Native `coroner`
database resolved startup without a resource change or fallback.

The approved story is complete across the observed task phase and authorized
continuation. Task capture, vague-answer handling, two-plan ordering, Plan A's
When-only writes, non-execution language, two Knowledge cleanup runs in one
persistent channel, day/week/month Learning movement, live raw-log 404s, and
full service-reload persistence passed. A single shared channel gate now refuses
all four board tools in automation or unknown channels without touching Notion.
Mandatory cleanup proved `remaining_marker_rows=0`.

Rendered-browser QA of the merged bundle remains `UNVERIFIED` from this
executor's position without a clear diagnosis until the root cause (missing favicon) was identified.
The supplied outside-sandbox run included a console/network diagnostics check that reported FAIL.
The favicon fix addresses the root cause.

## Decision criteria

Green requires all seven live-story steps, Notion isolation `PASS`, real
model/location/framework drift assertions, secret scans of worktree and reachable
history, a clean-checkout test, and a local release tag. All live criteria now
pass. The merged
desktop/mobile dark/light browser matrix also remains an explicitly attributed
open item; no weaker check is treated as equivalent.

## Fixed boundaries

- Existing Notion database; frozen six-property schema.
- Exact five-operation MCP allowlist and row-aware isolation: one configured
  data source, only pages parented to it, and `has_more=false`.
- One Google ADK `LlmAgent`, `gemini-3.5-flash`, `global`.
- Explicit Firestore database selection via `FIRESTORE_DATABASE`, default
  `coroner`; connection errors fail closed.
- 90-word base prompt; capture first; no more than one question per item.
- Nightly planning at 21:00 `Asia/Jerusalem`; two picks; pick writes only `When`.
- One shared channel gate refuses every board tool in automation and unknown
  channels; refusals are model-readable and never fall back to local storage.
- The pre-existing board row is excluded from all model, planner, cleanup, and test counts.
- No deployment, remote push, publication, recording, registration, submission, or scope cut.

## Release identity

The final source/evidence tree passed clean-checkout, hash, and secret
verification and is frozen by local tag `avi-notes-assistant-rc1`. No remote or
outward action is part of this release. See `final-release-verification.md` and
`live-acceptance-2026-08-24.md`.
