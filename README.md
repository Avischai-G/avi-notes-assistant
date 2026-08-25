# Agentonomy Tasks

Live deployment: https://avi-notes-assistant-295057934762.us-central1.run.app

A small chat and live-voice assistant for capturing tasks into one scoped Notion database, with automations that review the board on a schedule. It organises records; it never claims to perform the underlying work.

To connect your own Notion board from scratch, see [docs/SETUP-NOTION-FROM-SCRATCH.md](docs/SETUP-NOTION-FROM-SCRATCH.md).

The release candidate reuses Coroner's proven FastAPI, Cloud Run, Google ADK, Vertex AI, and Firestore stack. The former product remains available only in git history and the local `pre-rebuild` tag.

## Product behaviour

- The model distinguishes something Avi wants to remember or do from ordinary conversation. It writes tasks, leaves plain chat alone, and calls the day planner when he asks for a plan or says where he will be tomorrow.
- It captures first, then proactively asks the one short question a task genuinely needs; a vague answer keeps the stated default.
- Nothing is invented: a task gets `Not started` and whatever Avi actually said.
  No date, place or duration is guessed, and free text goes on the task's own
  page rather than into a property he cannot sort or filter on.
- `Organize tasks` reviews the board weekly for duplicates, items past their
  date, titles too vague to act on, and titles hiding more than one action. It
  reports and changes nothing: only Avi knows which copy of a duplicate to keep.
- The chat can list and run automations by name.
- Automation channels cannot access any board or planning tool. One shared channel gate
  returns a model-readable refusal without calling Notion; unknown channel
  identity also denies.
- Every automation carries a structured trigger — hourly, daily or weekly, plus
  when — and one derived sentence (`Daily at 21:00`) for display. Nothing is
  special-cased: an automation is due when its own `next_run_at` arrives.
- The organiser's learning event log stays in-process. There is no Learning page
  and no browser route that reads it.

## Architecture

See [docs/architecture.md](docs/architecture.md). The model-backed request path contains exactly one Google ADK `LlmAgent`, model `gemini-3.7-flash`, location `global`, and twelve gated tools: create, rename, change fields/Status, list, search, read/write details pages, delete/restore, comments, and plan tomorrow. There is no regex pre-router.

## Local offline setup

Requirements: Python 3.12+, Node 20+, and npm.

```sh
./setup.sh
USE_FIRESTORE=0 \
TASK_STORE_MODE=fake \
CORONER_KNOWLEDGE_ROOT=.knowledge \
./.venv/bin/uvicorn server:api --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. This mode uses deterministic local stores and does not contact Notion, Firestore, Vertex, or Cloud Storage until a model- or embedding-backed action is explicitly invoked.

Run the offline acceptance suite:

```sh
./.venv/bin/python -m pytest -q
node --check web/app.js
```

The browser suite is `npm run test:ui`. It tests a 2x2 matrix (dark/light theme x desktop/mobile viewport) plus keyboard and accessibility, running 9 checks total: chat interface, editor interface, and console/network diagnostics. Its test-only app uses a mocked model and a synthetic fake-store row; it makes no Vertex or Notion call.

Start the server first with the required environment variables:

```sh
BUILD_REVISION=avi-notes-assistant-rc4-ui USE_FIRESTORE=0 TASK_STORE_MODE=fake \
CORONER_KNOWLEDGE_ROOT=.knowledge \
./.venv/bin/uvicorn tests.ui_browser_app:api --host 127.0.0.1 --port 8764
```

Then run the suite in a separate terminal:

```sh
npm run test:ui
```

Use only one server on port 8764. The suite checks `/api/health` before opening Chrome and fails if `build_revision` is not `avi-notes-assistant-rc4-ui`, preventing a stale process on that port from passing silently.

The suite requires:
- a running server at `UI_BASE_URL` (defaults to `http://127.0.0.1:8764`)
- system Google Chrome at a macOS path (set via `CHROME_PATH` env var, defaults to `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`)

Automations are automatically registered when the server starts. The suite verifies two automation channels: "Knowledge cleanup" and "Plan tomorrow".

## Local authenticated setup

The user-owned file `~/.config/agentonomy/notion.env` must be a regular mode-`0600` file containing exactly `NOTION_TOKEN` and `NOTION_TASKS_DATABASE_ID`. Never echo either value.

Verify isolation and the pinned five-operation MCP surface before starting the app:

```sh
./.venv/bin/python scripts/notion_board_setup.py isolation
./.venv/bin/python scripts/notion_board_setup.py discover
```

Then source the file without printing it and run with the eligible Vertex configuration:

```sh
set -a
. "$HOME/.config/agentonomy/notion.env"
set +a
GOOGLE_CLOUD_PROJECT=gen-lang-client-0256233370 \
GOOGLE_CLOUD_LOCATION=global \
GOOGLE_GENAI_USE_VERTEXAI=true \
FIRESTORE_DATABASE=coroner \
USE_FIRESTORE=0 \
TASK_STORE_MODE=notion \
./.venv/bin/uvicorn server:api --host 127.0.0.1 --port 8000
```

An authenticated model or embedding call may bill the configured Google Cloud account. Notion writes persist. Run the live acceptance story only after the separate explicit approval described in `docs/LIVE-ACCEPTANCE.md`.

## Deploying

`gcloud run deploy --source .` uploads whatever is on disk at that second, not
the last commit. On 2026-08-24 a deploy landed between two edits of the same
change and shipped revision `00004-mzw` with a new `web/index.html` against the
previous `web/app.css`, which left the live page unstyled. So: commit first,
confirm `git status` is clean, run `pytest` and `npm run test:ui`, and only then
deploy — and never start a deploy while another session is mid-edit.

The live revision is behind `main` until the next deploy runs.

## Cloud Run configuration

The container is prepared for the existing Cloud Run/FastAPI shape, but this repository does not create or change cloud resources.

The approved deployment is live at the URL above. Its runtime provides:

- project `gen-lang-client-0256233370` and `GOOGLE_CLOUD_LOCATION=global`;
- `FIRESTORE_DATABASE=coroner`, selecting the existing Firestore Native database
  for channels, automation state, embedding metadata, and private learning-event metadata;
- one dedicated writable Cloud Storage volume mounted at `/knowledge` for Markdown bodies;
- `NOTION_TOKEN` and `NOTION_TASKS_DATABASE_ID` through approved secret references, never environment literals in a command or manifest;
- `TASK_STORE_MODE=notion`, `GOOGLE_GENAI_USE_VERTEXAI=true`, and `CORONER_MODEL=gemini-3.7-flash`;
- the existing scheduler, only after separate approval, targeting `POST /api/automations/tick`.

Building an image locally is non-deploying:

```sh
docker build -t avis-notes-assistant:rc .
```

Deployment, resource creation, scheduler mutation, repository publication, recording, and submission are separate approval gates and are intentionally absent from this release procedure.

## Notion boundary and residual exposure

The database already exists. Its frozen properties are `Name`, `Status`, `When`, `Place`, `Minutes`, and `Notes`; `Status` accepts only `Not started`, `In progress`, or `Done`. No database, schema, data-source, or view creation operation exists in the app.

The pinned local MCP child exposes exactly the compiled allowlist: `create_page`, `set_page_title`, `set_page_property`, `query_database`, `archive_page`, `restore_page`, `get_page_markdown`, `update_page_markdown`, `add_page_comment`, and `list_comments`. The organiser receives four TaskStore tools plus the deterministic tomorrow-planning tool, and never receives raw MCP or archive access. The planner accepts only recent board Place values plus `Anywhere`.

This is strong grant scoping, not perfect isolation. The token can currently see the configured database's schema and every current or future row, and its allowed MCP surface can create, rename, change properties, query, and archive rows. Someone with permission to edit the Notion connection could later widen Content access. The permanent unfiltered-search regression therefore hard-fails unless it returns exactly one configured data source, every other result is a page parented to that same data source, and `has_more` is false. Full details are in [docs/NOTION-SETUP.md](docs/NOTION-SETUP.md).

## Demo materials

- [Devpost draft](docs/DEVPOST-DRAFT.md)
- [Synthetic demo reset](scripts/demo_reset.py)
- [Sub-four-minute shot list](docs/SHOT-LIST.md)
- [Live acceptance gate](docs/LIVE-ACCEPTANCE.md)
