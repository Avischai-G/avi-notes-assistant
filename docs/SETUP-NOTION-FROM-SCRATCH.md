# Connect your own Notion board from scratch

Agentonomy Tasks talks to exactly **one** Notion database through an internal
integration. The integration can only see pages you explicitly share with it —
the rest of your Notion account stays completely private. Setup takes about
five minutes.

## 1. Create the integration

1. Go to https://www.notion.so/my-integrations and click **New integration**.
2. Name it (e.g. `Agentonomy Tasks`), pick your workspace, type **Internal**.
3. Under Capabilities, enable **Read content**, **Update content**, and
   **Insert content**. Leave user-information capabilities off.
4. Copy the **Internal Integration Secret** (starts with `ntn_` or `secret_`).
   This is your `NOTION_TOKEN`. Never paste it anywhere except the environment
   configuration in step 4.

## 2. Create the task database

1. In Notion, create a new page with a **Table** (full-page database).
2. Give it exactly these properties (names and types matter — the schema is
   validated at startup):

   | Property | Type |
   |---|---|
   | `Name` | Title |
   | `Status` | Status (`Not started`, `In progress`, `Done`) |
   | `When` | Date |
   | `Place` | Select |
   | `Minutes` | Number |

   A `Notes` (Rich text) column is optional; the app detects whether it exists.

## 3. Share the database with the integration

1. Open the database page → **⋯** menu → **Connections** → add your
   integration.
2. This is the privacy boundary: the integration can now read and write **this
   page and its children, and nothing else** in your workspace. Don't connect
   it to any other page.
3. Copy the database ID from the page URL: the 32-character hex string before
   any `?` — `https://notion.so/yourname/<DATABASE_ID>?v=...`. This is your
   `NOTION_TASKS_DATABASE_ID`.

## 4. Give the app the two values

Local run — create `~/.config/agentonomy/notion.env` with mode `0600`:

```dotenv
NOTION_TOKEN=<your integration secret>
NOTION_TASKS_DATABASE_ID=<your database id>
```

Cloud Run — store the token in Secret Manager and reference it, keep the
database ID as a plain env var:

```sh
gcloud secrets create notion-token --data-file=- <<< "$NOTION_TOKEN"
gcloud run services update YOUR_SERVICE --region us-central1 \
  --update-secrets NOTION_TOKEN=notion-token:latest \
  --update-env-vars NOTION_TASKS_DATABASE_ID=<your database id>
```

The token is only ever passed through the environment to the pinned local
Notion MCP child process — never as a command argument, prompt value, or log
field. Startup fails closed if either value is missing or malformed, and a
startup guard verifies the MCP tool allowlist before serving traffic.

## Safeguards to keep in mind

- **Scope**: everything on the shared board is visible to the app (and to
  anyone you show it to in a demo) — but nothing outside it is reachable, even
  in principle: `search_pages` is on the forbidden-operation list precisely so
  the app can never enumerate the rest of a workspace.
- **Making the board page public** (Share → Publish) only publishes that page
  for viewing; it grants the integration nothing extra and exposes no other
  page of your account.
- Rotating the token in the Notion integration settings instantly cuts off any
  leaked copy.
