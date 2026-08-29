# Devpost draft — Agentonomy Tasks

## Tagline

Say the messy thought. Get one short line back — and a Notion board that
stays in order without ever being guessed at.

## Why it should win

- **Genuinely agentic, not a chat loop.** Two Google ADK agents cooperate:
  a live voice navigator hands work to the task organizer mid-conversation,
  watches the chat play it out — instruction bubble, thinking ball, answer —
  and speaks the result back, while scheduled automations work the same
  board in the background through the very same gated tools.
- **Runs without anyone watching.** Cloud Scheduler ticks the service;
  automations fire on their own structured triggers, and due reminders ring
  every enrolled phone by Web Push — app closed or not — with Snooze/Done
  actions, then file a ⏰ comment as the durable record.
- **Nothing hardcoded.** Every behavior — both agents' instructions, each
  automation's prompt and schedule, the user memory, even which Notion board
  the app writes to — is editable from the phone, live, with no redeploy.
- **Security as a feature.** One database, a compiled ten-operation MCP
  allowlist that fails closed on drift, a permanent isolation regression,
  channel-gated tools, write-only secrets, and a device-local API key model
  where the server never stores a user's key.
- **Product-grade polish.** Installable PWA, dark/light/system themes,
  device-timezone truth for every displayed time, any-language answers in
  text and speech, and 165 unit tests plus a browser matrix across both
  themes and both viewports.

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
and restores tasks, ticks checklist items, and comments; a photo sent with a
message can be attached straight onto a task's page; and "remind me about X
at 10" sets a timed reminder, stored in the board's optional `Reminder`
date column. When it fires, the app itself pushes a notification to every
enrolled device — Web Push through the PWA's service worker, phone closed or
not — with Snooze 10 min and Done buttons, groups several due reminders into
one listed notification, leaves a ⏰ comment on the task as the durable
record, and clears the column, so the board shows only what is still
pending. General questions — facts, news,
weather — get Google-Search-grounded answers with sources, and both agents
answer in whatever language they are addressed in.

**A weekly board review you own.** The shipped `Organize tasks` automation
asks the model once a week for near duplicates, items past their date,
titles too vague to act on, and titles hiding more than one action — and
proposes rather than changes, because only the person who wrote a duplicate
knows which copy is the keeper. Nothing about it is special-cased: like any
automation you create, its prompt can be reworded, its schedule moved, or
the whole thing deleted for good. The chat can also list automations and
run any of them on demand by name.

**Structured automation triggers.** Automations can be created and edited in
the app, each with its own prompt and a structured trigger — frequency, hour,
minute, weekday — plus one derived display sentence (`Weekly on Sunday at
09:00`). Nothing is special-cased: an automation is due exactly when its own
`next_run_at` arrives, fired on schedule by Cloud Scheduler. Time belongs
to the device, not the server: chat dates resolve in the phone's timezone,
and each automation fires on the clock of the device that scheduled it,
displayed in the viewer's local clock with a quiet hint naming its origin. Automation
turns use the same gated tools as the chat, so a scheduled prompt can really
work the board; unknown channel identity still fails closed, and an
automation can never start another automation.

**Live voice navigator.** A hands-free voice session on
`gemini-live-2.5-flash` streams microphone audio over a WebSocket and answers
in speech. The navigator hands board work to the task assistant with
`send_task_to_chat` — the open chat renders the instruction and thinking
animation the moment it lands, exactly as if typed, and quick answers are
read straight back — while `navigate` and `run_automation` drive the app
itself. Its own tools read the board, answer any question about the world
through Google-Search-grounded `web_search`, and read and write the same
capped user memory the chat uses. It can never change the board directly;
everything it hands over plays out in the visible chat, so nothing happens
behind your back.

**Personal memory.** Say "remember that I answer in short sentences" — to
either agent, typed or spoken — and it is stored — one plain-text memory with a hard word cap, injected into
the system prompt only when non-empty, so personalization never bloats the
context. The agent rewrites the whole memory on each change (the cap forces
it to condense, not accumulate), and "forget everything" wipes it — a clean
handover for the next owner. Only what the user explicitly asks to keep is
stored.

**A settings hub that owns the whole configuration.** Settings opens as five
full-screen sections. *Agent memory* shows everything the agent knows as one
editable field. *Model setup* holds the device-local Gemini API key — kept
only in that browser's `localStorage`, riding each request as a header,
funding a per-key agent instance, never persisted server-side — plus the
chat model and a Check button that verifies key and model with one live
call; with no key the app runs on the server's own Vertex AI credentials.
*Live agent* chooses the voice and the
navigator's instructions — role, style and operating rules in one editable
text, so no behavioral rule is hardcoded; the spoken language follows the
user automatically, constrained to the languages they name. *Notifications* enrolls the device
for Web Push, so due reminders ring it directly. *Notion integration* connects the app to
any board from the UI: paste the integration secret and the database ID — a
visual guide shows exactly where in the board's URL the ID lives — and Save
validates the board with one read before switching. Every prompt, including
each automation's, is editable in place.

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
- The organizer's tool surface is fourteen typed board tools — create, rename,
  move fields/Status, list, search, read/write details pages, tick checkboxes,
  attach files, set reminders, delete/restore, comments — plus `web_search`
  (a nested Google-Search-grounded model call), `notify` (an immediate push
  to every enrolled device), `remember`/`clear_memory` for the capped user
  memory, and `list_automations`/`run_automation`, every one behind the same
  channel gate.
- A pinned local stdio Notion MCP child exposes exactly a compiled ten-operation
  allowlist (`create_page`, `set_page_title`, `set_page_property`,
  `query_database`, `archive_page`, `restore_page`, `get_page_markdown`,
  `update_page_markdown`, `add_page_comment`, `list_comments`) against one
  database; startup discovery validates the exact tool set and fails closed
  on drift. Workspace-wide search is on the forbidden-operation list, so the
  app can never see past the one board shared with its integration.
- Web Push rides the PWA's service worker: the app generates its own VAPID
  identity once, keeps it in settings, and the scheduler tick notifies every
  enrolled device when a reminder is due — pruning subscriptions that died.
- Firestore persists channels, automation records and triggers, and settings.
- The Notion token arrives through a Secret Manager reference, never an
  environment literal in a command or manifest, and is never placed in a
  prompt or command argument.

## Data sources

The user's own Notion tasks database is the app's data store,
connected through an internal Notion integration — the app reads and writes
that single board and nothing else, enforced by a permanent unfiltered-search
regression that hard-fails unless every reachable result belongs to the one
configured data source. Application state (channels, automations, settings)
lives in Firestore; a device-local API key lives only in
that browser's `localStorage`. General questions are answered with Google
Search grounding through Gemini, with sources cited. No other third-party
datasets are used.

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
- A review automation that earns trust by proposing and never writing — and
  no behavior hardcoded: every automation, the shipped one included, is an
  editable prompt the user can reword, reschedule, or delete.
- Hands-free operation: the voice navigator hands work to the task assistant,
  reads quick answers back, and never claims to have done the work itself.
- A device-local key model that lets any phone fund its own model calls
  without the server ever storing a secret for it.
- Everything is a setting: prompts, operating rules, memory, languages, and
  the Notion board itself can all be changed from the UI — no redeploy to
  change how the app behaves.
- Regression checks for the frozen Notion schema, the exact MCP allowlist, and
  one-database isolation, plus a browser suite covering both themes and both
  viewports.

## What we learned

The strongest assistant behavior comes from narrow deterministic tools around
the model: defaults, trigger arithmetic, and channel permissions stay in
code, while the model handles the genuinely linguistic work of telling a
task from conversation. Structured trigger data beats
free-text schedules — a derived display sentence can never disagree with when
the automation actually fires. Saying less is a feature: a one-line reply is
what makes capture feel instant. And a review that only proposes is one
the user can safely leave running forever.

## What's next

Letting the review automation propose one-tap fixes (still applied only on
explicit confirmation), richer voice flows for working through the board
hands-free, and more user-defined automations built on the same structured
trigger model.

## Links

- Repository: https://github.com/Avischai-G/avi-notes-assistant
- Live app: https://agentonomy-tasks-295057934762.us-central1.run.app
- Demo video: `[to be added]`
