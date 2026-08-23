# Devpost draft — Avi's Notes Assistant

**Draft only. Unpublished. Repository, live-app, and video URLs remain blank.**

## Tagline

Say the messy thought. Get the useful note, the right defaults, and two honest
plans for tomorrow.

## Inspiration

Most task systems make capture feel like form-filling: choose a status, date,
place, estimate, and category before the thought is safely written down. Avi's
Notes Assistant reverses that order. It captures first, states the defaults it
used, and asks no more than one genuinely useful question.

## What it does

Avi speaks naturally in one task chat. A plain reminder becomes a row in his
existing Notion board immediately, with `Not started`, `Anywhere`, 30 minutes,
his original wording in Notes, and tomorrow as the default date. If his answer
to the one follow-up is vague, the assistant keeps that default, says so once,
and moves on.

At 21:00 in `Asia/Jerusalem`, the assistant can turn matching open tasks into
exactly two eight-hour day plans: heavy-first and light-first. The plans include
only the selected place and `Anywhere`; choosing one writes only `When`.

The same organiser maintains small Markdown skills, explicit rules, and dream
notes. A persistent Knowledge cleanup channel consolidates pending observations.
The Learning view shows day, week, and month aggregates while the detailed event
log stays agent-only.

The assistant organises records. It never claims to call, send, book, file, or
otherwise perform Avi's underlying work.

## How we built it

- FastAPI serves a no-build responsive browser UI and streams chat events over SSE.
- One Google ADK `LlmAgent` runs `gemini-3.5-flash` on Vertex AI in `global`.
- Four typed board tools sit above a fail-closed Notion adapter.
- A pinned local stdio MCP child exposes only five operations against one existing database.
- Firestore persists chats, automation state, learning-event metadata, and embedding metadata.
- Markdown knowledge uses a `/knowledge` filesystem contract intended for a dedicated Cloud Storage mount.
- `gemini-embedding-001` supplies semantic retrieval for the small knowledge set.

## Safety and privacy boundaries

The Notion token is never placed in a prompt or command argument. Startup fails
closed when model, location, task-store mode, credentials, database ID, discovery,
or isolation drift. The browser receives aggregate learning figures only; there
is no raw-log route. The integration can still read and mutate every row shared
with its configured Notion connection, so connection access remains a meaningful
residual trust boundary.

## Accomplishments

- Capture-before-question with a 90-word system prompt.
- Exactly one eligible ADK model agent and a deliberately narrow tool surface.
- Deterministic planning, vague-answer handling, and no-work cleanup paths.
- Persistent task and automation channels without a history sidebar.
- A dark/light, desktop/mobile interface designed for keyboard use.
- Regression checks for the frozen Notion schema and one-database isolation.

## What we learned

The strongest assistant behavior often comes from deterministic boundaries around
the model: capture policy, defaults, planning order, task ownership, and no-work
decisions are code, while the model handles natural language inside that envelope.
We also learned to keep deployment, publication, submission, and live-account
verification as separate evidence claims.

## What's next

After separate approval: deploy the prepared container with its Firestore and
Cloud Storage bindings, verify the public endpoint from outside the build
environment, record the synthetic demo, publish the repository, and submit the
exact reviewed Devpost payload. None of those outward actions has happened yet.

## Links

- Repository: `[not published]`
- Live app: `[not deployed]`
- Demo video: `[not recorded]`
