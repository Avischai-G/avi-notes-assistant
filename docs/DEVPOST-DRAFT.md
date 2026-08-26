# Devpost draft — Agentonomy Tasks

## Tagline

Say the messy thought. Get one short line back — and a Notion board that
stays in order without ever being guessed at.

## Inspiration

Most task systems make capture feel like form-filling: choose a status, date,
place, estimate, and category before the thought is safely written down.
Agentonomy Tasks reverses that order. It captures first, replies in one short
line, and asks a question only when the task is unusable without the answer —
and then exactly one.

## What it does

**One-line-reply task chat.** You speak naturally in one chat. A reminder
becomes a row on your existing Notion board immediately, and the reply is a
single line — "Added Grocery list." — not a recitation of fields. The board
keeps only properties you can sort or filter on: `Name`, `Status`, `When`,
`Place`, and `Minutes`. Nothing is invented: a date, place, or duration is
written only when you actually gave one, and anything free-form — your own
wording, context, links, checklists — goes on the task's own Notion page, not
squeezed into a property. The same chat searches, renames, corrects, deletes
and restores tasks, ticks checklist items, and comments — and a photo sent
with a message can be attached straight onto a task's page.

**Weekly deterministic board review.** The built-in `Organize tasks`
automation runs a weekly `BoardReview`: pure deterministic code that scans
open tasks for near duplicates, items past their date, titles too vague to
act on, and titles hiding more than one action. It reports and changes
nothing — only the person who wrote a duplicate knows which copy is the
keeper. The chat can also list automations and run any of them on demand by
name.

**Structured automation triggers.** Automations can be created and edited in
the app, each with its own prompt and a structured trigger — frequency, hour,
minute, weekday — plus one derived display sentence (`Weekly on Sunday at
09:00`). Nothing is special-cased: an automation is due exactly when its own
`next_run_at` arrives, fired on schedule by Cloud Scheduler. Automation
turns use the same gated tools as the chat, so a scheduled prompt can really
work the board; unknown channel identity still fails closed, and an
automation can never start another automation.

**Live voice navigator.** A hands-free voice session on
`gemini-live-2.5-flash` streams microphone audio over a WebSocket and answers
in speech. The navigator drives the app through three action tools —
`send_task_to_chat` (hand an instruction or question to the task assistant,
waiting a beat so quick answers are read straight back), `navigate` (jump to
the chat, an automation channel, or Settings), and `run_automation` — plus
read-only board lookups so it can answer "what's on my board?" directly. It
can never change the board itself; every request it hands over lands in the
visible chat with its answer, so nothing happens behind your back.

**Personal memory.** Say "remember that I answer in short sentences" and the
agent stores it — one plain-text memory with a hard word cap, injected into
the system prompt only when non-empty, so personalization never bloats the
context. The agent rewrites the whole memory on each change (the cap forces
it to condense, not accumulate), and "forget everything" wipes it — a clean
handover for the next owner. Only what the user explicitly asks to keep is
stored.

**Settings with device-local key layering.** A Gemini API key pasted into
Settings lives only in that browser's `localStorage`, rides each request as a
header, and funds a per-key organizer instance on the server. It is never
persisted server-side, and a Check button verifies the key and your chosen
chat model together with one live call. With no key, the app runs on the
server's own Vertex AI credentials. Settings also choose the chat model, the
live voice and its language, and the voice navigator's instructions; show the
agent's memory as an editable field; and can point the app at a different
Notion board by database ID, validated with one read before switching. Every
prompt, including each automation's, is editable in place.

**Installable, themed app.** The frontend is a no-build PWA — manifest,
service worker, installable to a phone home screen — with dark, light, and
follow-the-system themes, responsive from desktop to mobile.

## How we built it

- FastAPI on Cloud Run (`us-central1`) serves a no-build vanilla JS/CSS PWA,
  streams chat over SSE, and carries the live voice session (PCM audio both
  ways) over a WebSocket.
- Two Google ADK `LlmAgent`s on Vertex AI at the `global` location: the task
  organizer on `gemini-3.7-flash` and the voice navigator on
  `gemini-live-2.5-flash`.
- The organizer's tool surface is thirteen typed board tools — create, rename,
  move fields/Status, list, search, read/write details pages, tick checkboxes,
  attach files, delete/restore, comments — plus `remember`/`clear_memory` for
  the capped user memory and `list_automations`/`run_automation`, every one
  behind the same channel gate.
- A pinned local stdio Notion MCP child exposes exactly a compiled ten-operation
  allowlist (`create_page`, `set_page_title`, `set_page_property`,
  `query_database`, `archive_page`, `restore_page`, `get_page_markdown`,
  `update_page_markdown`, `add_page_comment`, `list_comments`) against one
  database; startup discovery validates the exact tool set and fails closed
  on drift. Workspace-wide search is on the forbidden-operation list, so the
  app can never see past the one board shared with its integration.
- Firestore persists channels, automation records and triggers, and settings.
- The Notion token arrives through a Secret Manager reference, never an
  environment literal in a command or manifest, and is never placed in a
  prompt or command argument.

## Data sources

The only external data source is the user's own Notion tasks database,
connected through an internal Notion integration — the app reads and writes
that single board and nothing else, enforced by a permanent unfiltered-search
regression that hard-fails unless every reachable result belongs to the one
configured data source. Application state (channels, automations, settings)
lives in Firestore; a device-local API key lives only in
that browser's `localStorage`. No third-party datasets are used.

## Challenges

Getting live voice to work at all was an empirical hunt: no Gemini 3.x model
supports the Live API yet, and the Gemini API's live previews connected but
never answered when probed with real speech — so voice always runs on Vertex
with `gemini-live-2.5-flash`, even when a device key funds the text organizer.
On the deployment side, `gcloud run deploy --source .` uploads whatever is on
disk at that second; one deploy landed between two edits of the same change
and shipped a mismatched HTML/CSS pair, which taught us to commit, verify a
clean tree, and run the test suites before every deploy.

## Accomplishments

- Capture-before-question with one-line replies and a strict no-guessing rule:
  empty properties are treated as normal and correct.
- A deliberately narrow surface: one gated tool set, one ten-operation MCP
  allowlist, one database, and a gate that fails closed on unknown channels
  and stops automations from triggering each other.
- A deterministic weekly review that earns trust by proposing and never
  writing.
- Hands-free operation: the voice navigator hands work to the task assistant,
  reads quick answers back, and never claims to have done the work itself.
- A device-local key model that lets any phone fund its own model calls
  without the server ever storing a secret for it.
- Regression checks for the frozen Notion schema, the exact MCP allowlist, and
  one-database isolation, plus a browser suite covering both themes and both
  viewports.

## What we learned

The strongest assistant behavior comes from narrow deterministic tools around
the model: defaults, review heuristics, trigger arithmetic, and channel
permissions stay in code, while the model handles the genuinely linguistic
work of telling a task from conversation. Structured trigger data beats
free-text schedules — a derived display sentence can never disagree with when
the automation actually fires. Saying less is a feature: a one-line reply is
what makes capture feel instant. And read-only is sometimes the right power
level: a review that only reports is one the user can safely leave running
forever.

## What's next

Letting the review automation propose one-tap fixes (still applied only on
explicit confirmation), richer voice flows for working through the board
hands-free, and more user-defined automations built on the same structured
trigger model.

## Links

- Repository: https://github.com/Avischai-G/avi-notes-assistant
- Live app: https://agentonomy-tasks-295057934762.us-central1.run.app
- Demo video: `[to be added]`
