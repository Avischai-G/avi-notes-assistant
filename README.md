# Avi's Notes Assistant

Live deployment: https://avi-notes-assistant-295057934762.us-central1.run.app

A small chat assistant for capturing reminders in one scoped Notion database, keeping good defaults visible, and turning open tasks into two practical plans for tomorrow. It organises records; it never claims to perform the underlying work.

The release candidate reuses Coroner's proven FastAPI, Cloud Run, Google ADK, Vertex AI, and Firestore stack. The former product remains available only in git history and the local `pre-rebuild` tag.

## Product behaviour

- The model distinguishes something Avi wants to remember or do from ordinary conversation. It writes tasks, leaves plain chat alone, and calls the day planner when he asks for a plan or says where he will be tomorrow.
- It asks at most one useful question per item. A vague answer keeps the stated default and is never re-asked.
- Defaults are `Not started`, `Anywhere`, 30 minutes, Avi's wording in Notes, and tomorrow for a plain reminder.
- A 21:00 `Asia/Jerusalem` nightly sweep offers exactly two plans: heavy-first and light-first. Picking one changes only `When` for included tasks.
- Knowledge cleanup consolidates pending Markdown dream notes in one persistent automation channel. A no-work run is deterministic and makes no Gemini call.
- Automation channels cannot access any board or planning tool. One shared channel gate
  returns a model-readable refusal without calling Notion; unknown channel
  identity also denies.
- Learning shows day/week/month aggregates. The complete learning event log is available only in-process to the organiser; there is no raw-log browser route.

## Architecture

See [docs/architecture.md](docs/architecture.md). The model-backed request path contains exactly one Google ADK `LlmAgent`, model `gemini-3.5-flash`, location `global`, and five gated tools: create, rename, change fields/Status, list, and plan tomorrow. There is no regex pre-router.

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
node --check web/learning.js
```

The browser suite is `npm run test:ui`. It tests a 2x2 matrix (dark/light theme x desktop/mobile viewport) plus keyboard and accessibility, running 9 checks total: task interface, learning interface, and console/network diagnostics. Its test-only app uses a mocked model and a synthetic fake-store row; it makes no Vertex or Notion call.

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

## Cloud Run configuration

The container is prepared for the existing Cloud Run/FastAPI shape, but this repository does not create or change cloud resources.

The approved deployment is live at the URL above. Its runtime provides:

- project `gen-lang-client-0256233370` and `GOOGLE_CLOUD_LOCATION=global`;
- `FIRESTORE_DATABASE=coroner`, selecting the existing Firestore Native database
  for channels, automation state, embedding metadata, and private learning-event metadata;
- one dedicated writable Cloud Storage volume mounted at `/knowledge` for Markdown bodies;
- `NOTION_TOKEN` and `NOTION_TASKS_DATABASE_ID` through approved secret references, never environment literals in a command or manifest;
- `TASK_STORE_MODE=notion`, `GOOGLE_GENAI_USE_VERTEXAI=true`, and `CORONER_MODEL=gemini-3.5-flash`;
- the existing scheduler, only after separate approval, targeting `POST /api/automations/tick`.

Building an image locally is non-deploying:

```sh
docker build -t avis-notes-assistant:rc .
```

Deployment, resource creation, scheduler mutation, repository publication, recording, and submission are separate approval gates and are intentionally absent from this release procedure.

## Notion boundary and residual exposure

The database already exists. Its frozen properties are `Name`, `Status`, `When`, `Place`, `Minutes`, and `Notes`; `Status` accepts only `Not started`, `In progress`, or `Done`. No database, schema, data-source, or view creation operation exists in the app.

The pinned local MCP child exposes exactly `create_page`, `set_page_title`, `set_page_property`, `query_database`, and `archive_page`. The organiser receives four TaskStore tools plus the deterministic tomorrow-planning tool, and never receives raw MCP or archive access. The planner accepts only recent board Place values plus `Anywhere`.

This is strong grant scoping, not perfect isolation. The token can currently see the configured database's schema and every current or future row, and its allowed MCP surface can create, rename, change properties, query, and archive rows. Someone with permission to edit the Notion connection could later widen Content access. The permanent unfiltered-search regression therefore hard-fails unless it returns exactly one configured data source, every other result is a page parented to that same data source, and `has_more` is false. Full details are in [docs/NOTION-SETUP.md](docs/NOTION-SETUP.md).

## Demo materials

- [Devpost draft](docs/DEVPOST-DRAFT.md)
- [Synthetic demo reset](scripts/demo_reset.py)
- [Sub-four-minute shot list](docs/SHOT-LIST.md)
- [Live acceptance gate](docs/LIVE-ACCEPTANCE.md)
