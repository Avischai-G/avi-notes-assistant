# Release-candidate evidence — start here

## Current conclusion

The five card outputs are integrated in this workspace-local clone. The merged
offline suite passes: `69 passed, 1 skipped`; the skip is the credential-gated
Notion isolation regression. Live Notion, Firestore, Vertex, and persistence
remain `UNVERIFIED` until explicit approval. Rendered-browser QA of the merged
bundle is also `UNVERIFIED`: after Avi installed matching Playwright browsers,
the unchanged suite's system-Chrome process exited `SIGABRT` before context
creation in this sandbox.

## Decision criteria

Green requires all seven live-story steps, Notion isolation `PASS`, real
model/location/framework drift assertions, secret scans of worktree and reachable
history, a clean-checkout test, and a local release tag. The merged desktop/mobile
dark/light browser matrix remains an explicit open item under Avi's amendment; no
weaker check is treated as equivalent.

## Fixed boundaries

- Existing Notion database; frozen six-property schema.
- Exact five-operation MCP allowlist and exact one-data-source isolation regression.
- One Google ADK `LlmAgent`, `gemini-3.5-flash`, `global`.
- 90-word base prompt; capture first; no more than one question per item.
- Nightly planning at 21:00 `Asia/Jerusalem`; two picks; pick writes only `When`.
- The pre-existing board row is excluded from all model, planner, cleanup, and test counts.
- No deployment, remote push, publication, recording, registration, submission, or scope cut.

## Ready next action

Commit the prepared candidate and prove its offline setup from a clean checkout,
then present the exact one-time live transcript, mutation set, and call estimate
to Avi for an explicit yes. No outward live test will occur before that answer.
