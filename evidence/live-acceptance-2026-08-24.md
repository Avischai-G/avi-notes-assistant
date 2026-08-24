# Live acceptance attempt — 2026-08-24

Marker: `A16799E0-RC-20260823-01`. Avi explicitly approved this trace and no
other outward action.

## Observed preflight

```sh
./.venv/bin/python scripts/notion_board_setup.py isolation
./.venv/bin/python scripts/notion_board_setup.py discover
```

Observed:

```text
PASS: search returned only the configured data source and its pages
Operation access: 5/44 enabled (allow=create_page,set_page_title,set_page_property,query_database,archive_page; block=(none))
PASS: MCP tools and the five-operation allowlist are exact
```

The search was unfiltered and reported `has_more=false`. No secret value or
Notion object ID was printed or recorded.

## Approved preparation

```sh
./.venv/bin/python scripts/demo_reset.py prepare \
  --marker A16799E0-RC-20260823-01 --approved-live-test
```

Observed:

```text
PREPARED marker=A16799E0-RC-20260823-01 synthetic_rows=2
```

## Blocking startup result

The approved local service command used the documented project,
`GOOGLE_CLOUD_LOCATION=global`, `GOOGLE_GENAI_USE_VERTEXAI=true`,
`TASK_STORE_MODE=notion`, `USE_FIRESTORE=1`, the approved marker, and the
workspace-local knowledge root. It exited before listening on port 8765.

The first Firestore automation-document read raised:

```text
google.api_core.exceptions.FailedPrecondition: 400 The Cloud Firestore API is
not available for Firestore in Datastore Mode database
projects/gen-lang-client-0256233370/databases/(default).
```

The stack ends at `app/automations.py` `FirestoreAutomationStore.get()` during
`app/chat.py` `init_chat_stores(use_firestore=True)`. This is a live target-state
incompatibility, not an inferred application assertion. Per Avi's instruction,
the trace stopped immediately: no configuration change, fallback, retry, code
repair, or scope cut was attempted.

Consequently, the visible transcript, model responses, planning/pick behavior,
Knowledge runs, Learning movement, raw-log HTTP boundary, and restart persistence
were not exercised. No Vertex generation or embedding request ran; the HTTP
service never started. The knowledge root contains no files.

## Mandatory cleanup

```sh
./.venv/bin/python scripts/demo_reset.py cleanup \
  --marker A16799E0-RC-20260823-01 --approved-live-test
```

Observed:

```text
CLEAN marker=A16799E0-RC-20260823-01 archived_marker_rows=2 remaining_marker_rows=0
```

Cleanup was marker-scoped. The user-owned pre-existing row was not titled,
opened, edited, archived, or treated as residue in this evidence. The release
was not committed or tagged because the live story did not pass.

## Firestore configuration resolution

Avi/Main Orchestrator established that the existing named database `coroner` is
Firestore Native and authorized a configuration-only fix. `app/chat.py` now
reads `FIRESTORE_DATABASE`, defaults it to `coroner`, and passes it explicitly to
the sole Firestore client constructor. Focused tests passed and a resumed live
startup reached `Application startup complete` without requesting an index or
any cloud-resource change. See `firestore-database-audit.md`.

## Resumed approved trace

The original loopback port 8765 was occupied by a running sibling Card 4 server,
confirmed by its process working directory. The release service therefore used
the probe's existing `--base-url` option with port 8875. This changed only local
transport; the approved transcript, marker, external services, and mutation set
were unchanged.

An initial preparation attempt failed during its first marker query with a
redacted Notion MCP `internal_error`; source inspection confirmed the query
precedes every create. One identical retry succeeded:

```text
PREPARED marker=A16799E0-RC-20260823-01 synthetic_rows=2
```

The ordered probe and server request log prove these live assertions completed:

- the reminder was captured with `Not started`, tomorrow (`2026-08-25`),
  `Anywhere`, 30 minutes, the original wording, and the marker;
- the assistant stated the defaults in one line and asked once;
- `whatever` kept the default, stated that once, made no tool call, and did not
  re-ask;
- the Office request produced exactly two differently ordered plans containing
  only the three marker-owned Office/Anywhere rows, with Jerusalem-aware times;
- picking Plan A changed only `When` on those three rows;
- task history contained none of the forbidden execution claims;
- dream seeding increased day/week/month Learning totals by one.

## Genuine product-path failure

The first Knowledge cleanup consolidated the pending synthetic dream before its
model turn. During that model turn the shared task organizer unexpectedly invoked
`create_task`. The server recorded:

```text
app.notion_mcp.NotionMcpError: create_page failed (internal_error): request to
https://api.notion.com/v1/pages failed, reason:
```

The Knowledge endpoint returned HTTP 200, then the probe exited:

```text
ERROR: AssertionError:
```

No later endpoint was requested. From the probe order, the failure is confined
to the first cleanup response assertions; the first assertion able to fail after
the guaranteed `status`, `model_called`, and consolidation fields is the
requirement for useful text. The exact assertion line is `UNVERIFIED` because
the probe intentionally printed no traceback. The unexpected task-tool call is
directly verified by the ADK/server stack, independent of that line attribution.

Had Notion accepted the call, it would have added an unapproved fourth marker
row and exceeded the nine-operation mutation estimate. This is a product-path
defect, not evidence for a retry. Per Avi's standing instruction, no repair,
retry, fallback, or scope cut followed.

The second no-work cleanup, post-cleanup Learning totals, raw-log HTTP probes,
and service reload were not run. Firestore/channel and local knowledge writes
from the partial approved trace persist; exact Vertex generation and embedding
request counts were not instrumented and are `UNVERIFIED`.

## Resumed-trace cleanup

After stopping the service, the mandatory marker-only cleanup observed:

```text
CLEAN marker=A16799E0-RC-20260823-01 archived_marker_rows=3 remaining_marker_rows=0
```

Those were the two seed rows plus the captured plumber reminder. No unmarked row
was opened, titled, edited, archived, or treated as residue. No commit or RC tag
was created.

## Authorized automation-channel gate

Avi authorized one shared, channel-scoped gate around the organizer's complete
four-tool board surface. The implementation keeps one `LlmAgent`, one Runner,
the same four tool names, and the unchanged 90-word system prompt. It denies
`create_task`, `rename_task`, `move_task`, and `list_tasks` in every
`automation-...` channel and when channel identity is unavailable. A denial is a
tool result the model can read, not an exception.

Deterministic tests forced each of the four tools from
`automation-knowledge-cleanup`; every turn completed with useful text and the
Notion client recorded zero calls. A separate unknown-channel test also denied
before the Notion client. No board read exception was granted because Knowledge
cleanup receives its consolidation context directly and does not need the board.

## Authorized remaining trace — PASS

The continuation reused the previously proven task channel and began with zero
marker rows. It preserved the original probe assertions and added only a
test-harness `resume` phase for the remaining acceptance steps. Observed output:

```text
LIVE_STORY_RESUME_PRE_RELOAD=PASS cleanup_runs=2 learning_periods=3 raw_http_routes=404 marker_rows=0
```

Directly observed:

- the previous eight-message task history was present;
- the existing Knowledge automation history remained the exact prefix of the
  continued history;
- a new synthetic dream increased day/week/month totals by one;
- the first cleanup consolidated it, called the model, returned useful text,
  emitted no error, and left marker rows at zero;
- the model acknowledged that board access was unavailable in this channel and
  completed the knowledge report without a board mutation;
- consolidation increased all three period totals once more and increased
  `dreams_consolidated` once;
- the second cleanup returned exactly `status=no-work` and
  `model_called=false`, appended to the same channel, and left totals unchanged;
- `/api/learning/raw`, `/api/learning/events`, and `/api/learning/log` each
  returned HTTP 404;
- the knowledge skill existed with a stable SHA-256 and no pending dream;
- the marker-scoped row view remained empty.

The service was stopped and restarted with the same Firestore Native database
and local knowledge root. Observed output:

```text
LIVE_STORY_RELOAD=PASS chat=durable automations=durable learning=durable knowledge=durable
```

The health identity, task chat, automation channel and histories, automation
definitions, Learning aggregates, knowledge manifest/hash, and empty marker-row
view all matched the pre-reload snapshot.

The first final cleanup query hit the already-observed transient Notion MCP
`internal_error` before any archive. One identical retry observed:

```text
CLEAN marker=A16799E0-RC-20260823-01 archived_marker_rows=0 remaining_marker_rows=0
```

Together with the earlier cleanup of all three created rows, the approved live
story is complete and has zero marker residue. No Google Cloud resource was
created, changed, or deleted. No deployment, remote push, publication,
recording, registration, or submission occurred.
