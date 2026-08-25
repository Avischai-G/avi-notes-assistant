# Existing Notion task database

The task organiser uses the already-created workspace-level database granted to
the `Agent Task Organiser` internal connection. It never creates a database,
data source, view, property, page hierarchy, integration, or account.

The runtime launches the exactly locked `notion-mcp-server@2.13.0` (`awkoy`) as
a local stdio child through Google ADK. The connection token is inherited only
through the child environment. It is never an argument, prompt value, fixture,
log field, or repository setting.

## Fixed schema

The database schema is authoritative and must not be mutated:

| Property | Type | Adapter behavior |
|---|---|---|
| `Name` | title | task/reminder text; `rename_task` changes only this |
| `Status` | status | `Not started`, `In progress`, or `Done`; `move_task` changes only this |
| `When` | date | optional ISO-8601 date or datetime |
| `Place` | select | optional; existing values include `Home`, `Office`, `Out`, and `Anywhere`; new option names are permitted |
| `Minutes` | number | optional finite, non-negative estimate |
| `Notes` | rich_text | optional free detail, up to 2,000 characters per adapter write |

`create_task` defaults Status to `Not started` and may set all optional fields.
`list_tasks` returns every field and may filter by one exact Status.

## Local configuration

Install the locked dependencies from the application root:

```sh
npm ci --ignore-scripts
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

The user-owned file `~/.config/agentonomy/notion.env` must be a regular file
with mode `0600` and exactly these two keys:

```dotenv
NOTION_TOKEN=SET_LOCALLY
NOTION_TASKS_DATABASE_ID=SET_LOCALLY
```

Never paste or echo either value. The setup utility accepts neither value on
its command line and refuses extra active keys.

## Permanent isolation regression

Run:

```sh
./.venv/bin/python scripts/notion_board_setup.py isolation
```

The check sends `POST /v1/search` with `{"page_size":100}` using an in-memory
authorization header. It passes only when all of these are true:

- the response is HTTP 200;
- `results` contains exactly one object;
- that object is the database's sole `data_source` under the current API, and
  its normalized `parent.database_id` equals `NOTION_TASKS_DATABASE_ID`;
- `has_more` is exactly `false`.

Any count other than one is a hard failure. The response body and identifiers
are never printed.

## Exact MCP surface

Run:

```sh
./.venv/bin/python scripts/notion_board_setup.py discover
```

The local server must expose only `notion_describe` and `notion_execute`, with
exactly these ten operations:

```text
create_page,set_page_title,set_page_property,query_database,archive_page,restore_page,get_page_markdown,update_page_markdown,add_page_comment,list_comments
```

There is no environment-controlled allowlist. The application compiles this
list in code and passes it through a minimal child environment. Database,
data-source, schema, view, search, users, files, blocks, move, and all other
operations are absent. `archive_page` and `restore_page` reach the organiser
only as `delete_task` and `restore_task`, so a delete is always undoable.

Before rename or Status movement, the adapter queries the configured database
and requires exactly one matching row id. An arbitrary id that is not returned
by that database never reaches a mutating operation.

## Approved live smoke

The smoke test refuses to start if the board is not empty. It creates two
uniquely marked synthetic rows, exercises all six property mappings, renames
one row, moves that row from `In progress` to `Done`, and queries Status
filters. In a `finally` cleanup it archives only rows bearing its random marker
and then requires the board query to return exactly zero rows.

Run only under the explicit live-test approval:

```sh
./.venv/bin/python scripts/notion_board_setup.py live-smoke \
  --approved-live-tests
```

A mode-`0600` state file in `evidence/` preserves only the random smoke marker
if a run is interrupted. A resumed run rejects every non-marker row and never
blindly replaces an unknown-outcome create. The state file is deleted after a
verified zero-row cleanup.

## Runtime and residual exposure

Source the local file into the application process without displaying it, set
`TASK_STORE_MODE=notion`, and start the app. Missing or malformed token/database
configuration, package drift, or an unexpected MCP discovery surface fails
closed. Production never falls back to `FakeTaskStore`.

This is strong grant scoping, not perfect isolation. Today, search proves that
the token can see only the configured database. Within that database, the
connection can see its fixed schema and every current or future row and can
create, rename, change properties, and archive rows through the allowed server
operations. The organiser receives twelve typed board tools built on that
surface, and never raw MCP access.
Someone who can edit the Notion connection could later widen Content access;
the permanent isolation regression is intended to detect that change.
