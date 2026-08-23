# Avi's Notes Assistant

A small chat assistant for capturing reminders in one scoped Notion database, keeping good defaults visible, and turning open tasks into two practical plans for tomorrow. It organises records; it never claims to perform the underlying work.

The release candidate reuses Coroner's proven FastAPI, Cloud Run, Google ADK, Vertex AI, and Firestore stack. The former product remains available only in git history and the local `pre-rebuild` tag.

## Product behaviour

- A plain reminder is written before the assistant asks anything.
- It asks at most one useful question per item. A vague answer keeps the stated default and is never re-asked.
- Defaults are `Not started`, `Anywhere`, 30 minutes, Avi's wording in Notes, and tomorrow for a plain reminder.
- A 21:00 `Asia/Jerusalem` nightly sweep offers exactly two plans: heavy-first and light-first. Picking one changes only `When` for included tasks.
- Knowledge cleanup consolidates pending Markdown dream notes in one persistent automation channel. A no-work run is deterministic and makes no Gemini call.
- Learning shows day/week/month aggregates. The complete learning event log is available only in-process to the organiser; there is no raw-log browser route.

## Architecture

See [docs/architecture.md](docs/architecture.md). The model-backed request path contains exactly one Google ADK `LlmAgent`, model `gemini-3.5-flash`, location `global`, and four board tools: create, rename, change fields/Status, and list.

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

The prepared rendered suite is `npm run test:ui`. It needs browser binaries that
match the pinned `playwright-core` plus a runtime allowed to create a browser
context. The merged-bundle rendered run is currently `UNVERIFIED` in this managed
sandbox: Chrome exited `SIGABRT` before context creation even after the matching
binaries were installed. The exact open item is recorded in
[evidence/rendered-browser-open-item.md](evidence/rendered-browser-open-item.md).

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
USE_FIRESTORE=0 \
TASK_STORE_MODE=notion \
./.venv/bin/uvicorn server:api --host 127.0.0.1 --port 8000
```

An authenticated model or embedding call may bill the configured Google Cloud account. Notion writes persist. Run the live acceptance story only after the separate explicit approval described in `docs/LIVE-ACCEPTANCE.md`.

## Cloud Run configuration

The container is prepared for the existing Cloud Run/FastAPI shape, but this repository does not create or change cloud resources.

An approved deployment must provide:

- project `gen-lang-client-0256233370` and `GOOGLE_CLOUD_LOCATION=global`;
- one Firestore database for channels, automation state, embedding metadata, and private learning-event metadata;
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

The pinned local MCP child exposes exactly `create_page`, `set_page_title`, `set_page_property`, `query_database`, and `archive_page`. The organiser itself receives only four TaskStore tools and never receives raw MCP or archive access.

This is strong grant scoping, not perfect isolation. The token can currently see the configured database's schema and every current or future row, and its allowed MCP surface can create, rename, change properties, query, and archive rows. Someone with permission to edit the Notion connection could later widen Content access. The permanent isolation regression therefore hard-fails unless search returns exactly one object—the configured database's data source—with `has_more: false`. Full details are in [docs/NOTION-SETUP.md](docs/NOTION-SETUP.md).

## Demo materials

- [Devpost draft](docs/DEVPOST-DRAFT.md)
- [Synthetic demo reset](scripts/demo_reset.py)
- [Sub-four-minute shot list](docs/SHOT-LIST.md)
- [Live acceptance gate](docs/LIVE-ACCEPTANCE.md)
