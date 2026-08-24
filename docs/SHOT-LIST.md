# Demo shot list — one continuous 3:40 take

This script targets **3 minutes 40 seconds**, leaving 20 seconds below the
4-minute limit. Record the live execution as one continuous take, in English,
without pausing, cutting, or replacing an outcome. The current requirements also
call for visible Google Cloud proof and a publicly visible YouTube or Vimeo
upload. [source: Devpost](https://allthingsagentichackathon.devpost.com/rules "All Things Agentic Hackathon Official Eligibility and Rules")

Replace `<MARKER>` below with one approved synthetic marker before recording.

## Pre-flight — complete before pressing Record

- Obtain the separate approvals for live Vertex use, persistent Notion writes,
  recording, and publication. Prepare only the approved marker-owned demo rows.
- In a full-screen browser, open the deployed app at its live
  `https://<service-host>.run.app` URL in a new, empty Task channel. Keep this app
  tab on screen when recording begins.
- In the next browser tab, open
  `https://<service-host>.run.app/api/health`. Confirm that the same live
  `*.run.app` host is visible and the JSON shows `"ok": true`,
  `"model": "gemini-3.5-flash"`, `"location": "global"`,
  `"framework": "Google ADK"`, `"firestore_mode": "firestore"`, and a
  non-`local` `build_revision`.
- In the logged-in Notion desktop app, open a sanitized full-page view titled
  `Demo Task Board`. Collapse the sidebar and filter the view to `Notes contains
  <MARKER>`. Show only `Name`, `Status`, `When`, `Place`, and `Minutes`. Confirm
  that every visible row is synthetic and marker-owned.
- Prepare two marker-owned planning rows at `Office`, then preview the complete
  Office plan off camera. Do not record the planning shot unless every title in
  both plans is synthetic and marker-owned. If that privacy check cannot pass,
  use a dedicated synthetic-only demo board before recording.
- Open a clean, full-screen rendering of `docs/architecture.md`. Close
  notifications, password-manager prompts, bookmarks, developer tools, and all
  unrelated windows. Set a visible recording timer and test the microphone.
- Practise the tab/app switches and spoken lines once. The scheduled end is
  `3:40`; use the 20-second margin only for live loading or one refresh, and
  finish before `4:00`.

## Never show on screen

- Any token, API key, cookie, credential, secret, environment file, login form,
  or password-manager content.
- Any Google Cloud billing page or billing data.
- Any private Notion page title, database title, page/database ID, URL, sidebar,
  or unfiltered view.
- Any of Avi's real personal tasks. In particular, **`Call the accountant about
  the Q3 filing` must not appear anywhere in the recording**.
- Any terminal history, raw event log, private browser tab, notification, email,
  or personal account detail.

## Continuous-take script

| Start | Duration | Action and visible proof | Spoken narration — read aloud in English |
|---:|---:|---|---|
| 0:00 | 0:16 | Stay on the live Task app. Keep the `*.run.app` address visible and show the empty composer. | “Tasks disappear when capture feels like form-filling. Avi's Notes Assistant lets me say the messy thought first, then organises it in Notion. It never performs the underlying task.” |
| 0:16 | 0:18 | Switch to the preloaded `/api/health` tab. Hold on one frame containing the full live `https://…run.app/api/health` address and the verified health JSON. A judge should see `ok: true`, Gemini 3.5, `global`, Google ADK, Firestore mode, and the deployed revision together. | “This is the live Cloud Run backend. The run.app address and health response show the deployed revision, Google ADK, Gemini through the global configuration, and Firestore-backed state.” |
| 0:34 | 0:34 | Return to Task. Type and send: `Please remember this exact synthetic task: [<MARKER>] Buy demo tea.` Keep the streaming tool state and final reply visible. Expected: one created-task confirmation with the visible defaults and at most one question. | “I am giving it a natural note, not filling in fields. The model decides that this is a task, writes the record first, then shows every default it applied.” |
| 1:08 | 0:24 | Switch to the sanitized `Demo Task Board` in Notion. Refresh once if needed. Hold on the newly appeared marker-owned row and its real `Status`, `When`, `Place`, and `Minutes` values. | “This is the real Notion board mutation happening live. The new synthetic row is a record of work to do; the assistant has not bought the tea or claimed that it did.” |
| 1:32 | 0:18 | Return to Task. If the assistant asked one question, reply `whatever` and show that the default is kept with no second question. If it asked none, leave the composer untouched and continue. | “When one detail is useful, it can ask once. A vague answer keeps the stated default and ends the loop. If no question was needed, it simply moves on.” |
| 1:50 | 0:48 | Send `I will be at Office tomorrow.` Show both live plans, heavy-first and light-first, then activate `Pick Plan A`. Keep every displayed title within the preflight-approved synthetic set. | “The same model decides this is a planning request. It reads current Place values at runtime and offers two different schedules. I choose one; that changes only the tasks' When fields. It still executes none of them.” |
| 2:38 | 0:20 | Return to the sanitized Notion view and refresh once. Show only marker-owned rows. Hold on their updated `When` values; do not open a row. | “Back on the filtered board, the synthetic rows show the writes that actually happened. The assistant changed records only; it did not buy, send, draft, or complete anything for me.” |
| 2:58 | 0:30 | Show the prepared architecture rendering. Trace browser → Cloud Run/FastAPI → one Google ADK agent → Vertex AI → five gated tools → Notion, with Firestore and Cloud Storage beside the service. | “One FastAPI service on Cloud Run hosts one Google ADK agent. Gemini 3.5 runs through Vertex AI. Five gated tools reach the scoped Notion adapter, Firestore keeps channel state, and Cloud Storage backs knowledge. There is no regex pre-router.” |
| 3:28 | 0:12 | Return to the live Task result and end on the visible confirmation and plan controls. | “The value is simple: messy thought in, organised record and practical plan out, with narrow permissions and visible defaults. Avi remains in control and does the work.” |

Scheduled finish: **3:40**. Hard stop: **before 4:00**.

## Recovery lines — stay in the same take

- **Task was not created:** Say, “The model decides how to route language. That
  wording stayed in chat, so I will make the intent explicit and continue.” Then
  send `Create a task named exactly [<MARKER>] Buy demo tea.` Continue to the
  Notion shot; do not claim a write until the row is visible.
- **Notion row has not appeared:** Say, “The filtered board has not refreshed
  yet, so I will refresh it once and keep recording.” Refresh once and use the
  timing margin while the row loads. Keep any missing mutation visible and never
  describe it as successful.
- **No clarification question:** Say, “The model had enough context and did not
  need a question, so I will continue without inventing one.” Skip `whatever`.
- **First place statement does not produce plans:** Say, “The model chooses the
  route. That phrasing did not request a plan clearly enough, so I will make it
  explicit without cutting.” Send `Plan tomorrow for Office.` Then show and pick
  a plan if it appears; otherwise keep the actual response visible and continue.
- **Any unexpected or error response:** Say, “That is the live result. I will
  leave it visible and continue the same take.” Do not hide it, edit around it,
  or state that the missing action happened.

## After recording

- Verify the single continuous file is under `4:00`, the narration is English,
  the real Notion mutation is visible, and the Cloud Run frame shows both the
  live `*.run.app` address and health response.
- Review every frame for the prohibited material above. Do not use a take that
  exposes private data or credentials.
- After separate publication approval, upload the video to YouTube or Vimeo,
  make it **publicly visible** (not private or unlisted), verify that visibility
  while signed out, and place that public URL in the Devpost submission.
