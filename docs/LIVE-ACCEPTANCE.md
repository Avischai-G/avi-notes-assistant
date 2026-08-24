# One-time live acceptance gate

**State:** `PASS` on 2026-08-24 across the observed task phase and authorized
continuation. All seven steps passed, service reload passed, and final cleanup
proved zero marker-owned rows remain. See
`evidence/live-acceptance-2026-08-24.md`. Marker:
`A16799E0-RC-20260823-01`.

This procedure is the only approved live story for the release candidate. It is
not deployment, publication, recording, registration, or submission approval.

## Exact visible transcript and controls

The Task channel input will be exactly:

1. Avi: `remind me to call the plumber`
2. Expected assistant: `Noted — tomorrow, Anywhere, 30 min. Would a specific time tomorrow help?`
3. Avi: `whatever`
4. Expected assistant: `Kept the default — tomorrow, Anywhere, 30 min.`
5. Avi: `I will be at Office tomorrow.`
6. Expected assistant: two plans only — Plan A heavy-first and Plan B light-first — using only the marker-owned Office and Anywhere rows, with `Asia/Jerusalem` times.
7. Tester activates the visible `Pick Plan A` control once.
8. Observed assistant: `Plan A is set for 2026-08-25.`

Before that transcript, the reset script will create exactly two synthetic rows:

- `[A16799E0-RC-20260823-01] Draft release outline` — Office, 180 minutes.
- `[A16799E0-RC-20260823-01] Send synthetic update` — Anywhere, 15 minutes.

The live server wraps the real Notion adapter in a marker scope. Model tools and
the planner can neither observe nor mutate unmarked rows. The plumber row receives
the marker in Notes even though the visible input remains exact. Cleanup archives
only marker-owned rows and must prove zero marker rows remain.

The automation sequence will then:

1. capture one synthetic dream note carrying the same marker;
2. record Learning day/week/month totals;
3. run Knowledge cleanup in its persistent channel;
4. run it again and require `status=no-work` and `model_called=false`;
5. require both results in the same channel history;
6. require Learning totals to reflect the new dream and consolidation events;
7. request `/api/learning/raw`, `/api/learning/events`, and `/api/learning/log` over HTTP and require HTTP 404;
8. restart the local service and require task chat, both automation channels, their histories, Learning aggregates, and the knowledge file to survive.

The raw-log checks above prove the server-side HTTP boundary. They are not a
substitute for rendered-browser verification. The unchanged merged-bundle
browser suite remains `UNVERIFIED` in this sandbox because its system-Chrome
process aborted before creating a context; Card 2 and Card 4 had passed their
rendered checks independently before the merge.

## Call and persistence estimate

- Vertex generation: best estimate **3 requests** — usually two for the reminder
  tool call/follow-up and one for the first cleanup response. A realistic range is
  **3–5** because an ADK tool-followup can make more than one generation request.
  The vague reply, place planner, plan pick, and second no-work cleanup are
  deterministic and should make none.
- Semantic indexing: **up to four Vertex embedding requests** for the synthetic
  knowledge item and its retrieval query/cache path.
- Notion: **9 expected persistent mutation operations** — three creates, three
  `When` writes when Plan A is picked, and three archives during cleanup — plus
  scoped queries. Any unexpected marker-owned row is archived in the same cleanup.
- Firestore and the local knowledge directory receive persistent synthetic channel,
  automation, embedding-metadata, and learning-event writes.

Model and embedding calls can bill Avi's existing Google Cloud account. Notion
writes persist until archived. Firestore and knowledge writes also persist after
the service restarts. There is no approval here until Avi explicitly answers yes.

## Commands reserved for the approved run

These commands must not be run before approval:

```sh
export LIVE_ACCEPTANCE_MARKER=A16799E0-RC-20260823-01
export GOOGLE_CLOUD_PROJECT=gen-lang-client-0256233370
export GOOGLE_CLOUD_LOCATION=global
export GOOGLE_GENAI_USE_VERTEXAI=true
export TASK_STORE_MODE=notion
export USE_FIRESTORE=1
export CORONER_KNOWLEDGE_ROOT="$PWD/evidence/live/knowledge"

./.venv/bin/python scripts/notion_board_setup.py isolation
./.venv/bin/python scripts/notion_board_setup.py discover
./.venv/bin/python scripts/demo_reset.py prepare \
  --marker "$LIVE_ACCEPTANCE_MARKER" --approved-live-test
./.venv/bin/uvicorn tools.live_acceptance_app:api \
  --host 127.0.0.1 --port 8765
```

With that service running, the one-time probe command is:

```sh
./.venv/bin/python tools/live_acceptance_probe.py run \
  --marker "$LIVE_ACCEPTANCE_MARKER" --approved-live-test
```

Then stop and restart the same service command, and verify persistence with:

```sh
./.venv/bin/python tools/live_acceptance_probe.py reload \
  --marker "$LIVE_ACCEPTANCE_MARKER" --approved-live-test
```

After every assertion and the reload check, stop the service and run:

```sh
./.venv/bin/python scripts/demo_reset.py cleanup \
  --marker "$LIVE_ACCEPTANCE_MARKER" --approved-live-test
```
