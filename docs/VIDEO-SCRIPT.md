# Video script — read this aloud top to bottom (~3:50)

*Italic lines in brackets tell you what to show. Everything else you just read out loud.
Tabs to have open, in order: ① Cloud Run console ② the live app ③ `/api/health` ④ Notion (filtered demo board) ⑤ notion.so/my-integrations.*

---

*[Start on the live app, address bar visible, empty chat]*

Tasks die when capture feels like form-filling — status, date, place, category, before the thought is even safe. Agentonomy Tasks reverses that: I just say the messy thought, and an agent organises it into my real Notion board. It manages my records — I stay in control of the actual work.

*[Switch to the Cloud Run console tab]*

It runs on my Google Cloud project. This is the Cloud Run service — here are the deployed revisions, and this is the deploy screen I ship new versions from. *[open "Edit & deploy new revision", scroll once, close it — do NOT press the blue Deploy button]*

*[Switch to the /api/health tab, hold a few seconds]*

The health endpoint proves the stack live: Gemini 3.7 Flash through Vertex AI, the Google Agent Development Kit, Firestore for state — and the deployed revision right there in the JSON.

*[Back to the app. Type: "remind me to buy tea for the demo tomorrow at the office, should take 20 minutes" — send]*

I'm not filling in any fields. One ADK agent with twelve gated tools decides this is a task, writes it to Notion first, and answers in one line. It records only what I actually said — nothing gets invented, and extra detail goes on the task's own page instead of a property.

*[Switch to the filtered Notion board, refresh once, hold on the new row]*

And that's the real board mutation, live — Name, Status, When, Place, Minutes. The agent didn't buy the tea, and it doesn't claim it did.

*[Switch to notion.so/my-integrations, then briefly show the board's Connections menu]*

Anyone can point this at their own board in five minutes: create an internal Notion integration, make a table with these five columns, and connect the integration to that one page. That connection is the whole privacy boundary — the integration sees this page and nothing else in the account, and workspace-wide search is on the app's forbidden-operations list, so the rest of my Notion stays private by construction. The setup guide is in the repo.

*[Back to the app. Open the drawer, point at the automations]*

Automations live here, each with a structured trigger — hourly, daily, or weekly — fired on schedule by Cloud Scheduler. This one, Organize tasks, reviews the whole board weekly for duplicates, overdue items, vague titles, and titles hiding several actions — and it only proposes, because only I know which duplicate to keep. *[press Run on its row, show the report arriving]* I can also run any of these from chat, just by name.

*[Start a live voice session. Say: "Add a task: print the contest poster."]*

There's also a live voice mode — a real-time Gemini session over WebSockets. The voice agent is a navigator: it can read the board, hand work to the organiser, switch panes, or start an automation — nothing else. *[show the handoff landing in the chat]* And every request it sends to the organiser lands in this visible chat, with the answer — nothing happens behind my back.

*[Open Settings — the key shows only as dots, which is safe on camera. Point at the fields top to bottom, press Check, then cycle the theme once]*

The details are done properly too. The app runs on each user's own Gemini API key — stored only in this browser, shown masked, and this Check button verifies the key and my chosen model together with one live call. I can tell it what to call me, pick the chat model, the assistant's voice and accent — and every prompt, including each automation's, is editable in place. It installs as a progressive web app, follows system, light, or dark theme, and works on mobile.

*[Back on the chat, hold on the created task's confirmation]*

So: one FastAPI service on Cloud Run, one Google ADK agent on Gemini 3.7 Flash through Vertex, Firestore state, and a fail-closed Notion tool surface scoped to a single board. Messy thought in — organised, honest record out. I do the work; the agent keeps the books.

---

## If something goes wrong mid-take (keep recording)

- **Task didn't create:** "The model routes language itself — that stayed in chat, so I'll be explicit." Type: `Create a task: buy tea for the demo.`
- **Notion row not visible:** "The filtered view hasn't caught up — one refresh." Refresh once.
- **Voice hiccups:** "That's the live session — the text path you saw is the same agent." Move on.
- Never claim something worked that didn't.

## Never show on screen

An API key in plain text anywhere (the Settings field's dots are safe) · billing pages · terminals · notifications · your real personal tasks · the unfiltered Notion sidebar.

## Devpost checklist (verified 2026-08-25)

- ✅ Gemini 3.5+ via Vertex (`gemini-3.7-flash`, proven by `/api/health`)
- ✅ Google agent framework: ADK (in health JSON)
- ✅ Google Cloud infra: Cloud Run + Firestore
- ✅ Public repo, no secrets in files or git history (scanned), README spin-up steps
- ✅ Architecture diagram: `docs/architecture-diagram.png` — attach to the form
- ✅ Hosted project URL (the `*.run.app` address)
- ⚠️ Text description: rewrite `docs/DEVPOST-DRAFT.md` (still describes deleted features)
- ⬜ Video ~4 min, uploaded **public** on YouTube/Vimeo, visibility checked signed-out
- ⬜ Submit before **Aug 31, 2026, 5:00 PM PDT**
