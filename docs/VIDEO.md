# Demo video — shot list and narration

**Hard limit 4:00.** Budget **30–50 seconds** for live execution (measured: 28.4s–47.4s on the deployed service); **3:00–3:30** for narration and visual beats.

The video must be in English, must visibly show the hosted service on Google Cloud (`coroner-295057934762.us-central1.run.app`), and must be uploaded as **Public** on YouTube or Vimeo. Address bar and any identifying UI (run IDs, timestamps) are visible; no secret values or billing numbers on screen.

This shot list uses the rebuilt interactive autopsy UI. The featured run is "All six steps waiting on a human" (run `02266df1-6d2e-42be-8239-c243bd0896de`), which recorded itself as dead from a worker crash but the six agents overturned that verdict to prove it was stalled waiting for user input — the clearest evidence in the corpus that the adversarial design works.

**Exact timings come from a captured stream, not guesses.** Every number below is measured.

---

## 0:00–0:08 · The homepage (8 seconds)

**What's on screen:** Coroner homepage at `coroner-*.run.app`. Address bar visible. Dark theme, full viewport.

**What you click:** Click on sample run #2: "All six steps waiting on a human" (orange/yellow card).

**What you say:** "Coroner watches for agent runs that stop dead and says nothing. Six Gemini models work together to figure out what killed it. Watch a real autopsy."

**Notes:**
- The three sample cards are visible in the center of the screen ("Pick a dead run. It is autopsied live, in about thirty seconds.")
- Do not click "New autopsy" or anything else; go straight to sample #2.
- Landing page is the context — you're picking one of three pre-loaded cases to autopsy.

---

## 0:08–0:14 · Terminal view spawns with triage starting (6 seconds)

**What's on screen:** The terminal-style autopsy view materializes. Header reads `coroner://autopsy` with "Triage is running" and an elapsed-time counter starting at ~2.5s. The Triage row shows "proposes candidate causes" as the description. Below it, bracketed together, three investigation rows appear:

- Timeline lens
- Counterfactual lens
- Competing-explanation lens

All labeled as pending. Certification and Revival rows are grayed out below.

**What you click:** Nothing. Watch.

**What you say:** (Silence or very brief transition sound.) The UI is doing all the talking now — the timers and checkmarks are the narration.

**Notes:**
- The elapsed time on the right grows visibly (2.5s → 6.0s).
- Triage is the only agent working at this moment; the three investigators have not yet been assigned their tasks.
- Run clock ticks noticeably in the header.

---

## 0:14–0:22 · Triage completes; three investigators start in parallel (8 seconds)

**What's on screen:** At the 6.1-second mark (in the run's time, not wall clock):

- Triage row shows a **green checkmark** and "done" state.
- **Results expand** underneath: three cause hypotheses with confidence scores (STALLED_ON_USER 85%, USER_ABORT 0.1%, WORKER_TERMINATED 0.05%).
- The three investigator rows now show checkmarks and elapsed time (0.4s each) — they started simultaneously and are running in parallel.
- The three rows are visually grouped together with a bracket or distinct styling to show they run at the same time.
- Timers tick on the right for each investigator.

**What you click:** Nothing. Watch the three agents work.

**What you say:** "Triage found three possible causes. Now the three investigators attack them at the same time — each one tries to destroy the hypotheses from a different angle."

**Notes:**
- The three investigators have identical elapsed times because they start at the same instant (6.110s in the transcript).
- This is the visual proof of parallelism — if this moment is clear, the video's central claim (six agents, three in parallel) is proven.
- The triage results are visible and readable; they show the run recorded "WORKER_TERMINATED" but triage thinks "STALLED_ON_USER" is more likely.

---

## 0:22–0:37 · Investigators complete one by one (15 seconds)

**What's on screen:** The three investigators finish in sequence (not together). Watch them complete:

- Counterfactual lens finishes first (13.89s into the run, ~7.8s elapsed per investigator).
- Competing-explanation lens finishes next (14.47s, ~8.4s per investigator).
- Timeline lens finishes last (16.02s, ~9.9s per investigator).

Each shows:

- **Green checkmark** when done.
- **Results expand** showing "SURVIVED" and "REFUTED" verdicts for each hypothesis.
- The frame shows which causes survived the lens and which were destroyed.

All three sections are visible in the viewport at the same time so the viewer can see the verdicts stacking up.

**What you click:** Nothing. Let the results pour in.

**What you say:** "Each lens tries to break the hypotheses on a different axis. Timeline looks for the earliest divergence. Counterfactual asks 'what if we removed this cause?' Competing-explanation tries to build a rival story. All three agree on the winner."

**Notes:**
- Timers on the right show slight variance (7.8s vs. 9.9s) because the agents' actual work differs.
- All three arrive within the live window; no waiting between them.
- The key visual: STALLED_ON_USER survives all three lenses; the other two die. That's the proof.

---

## 0:37–0:45 · Certification runs (8 seconds)

**What's on screen:** The view has scrolled or the focus shifts to show:

- The three investigators are now all marked done with checkmarks collapsed.
- Certification row activates with a running state (timer shows ~6.5s elapsed).
- Description: "issues the death certificate."
- Below it, Revival is grayed out.
- The header still shows total elapsed time.

**What you click:** Nothing.

**What you say:** "The certifier reads the three lenses, applies the majority rule, and writes the death certificate."

**Notes:**
- Certification is not parallel; it waits for all three investigators to finish before starting (that's the architectural join point).
- The elapsed time (6.5 seconds in the run) should be visible and ticking.

---

## 0:45–0:52 · Certification completes (7 seconds)

**What's on screen:** Certification row shows:

- **Green checkmark** and "done" state.
- **Results expand** showing: cause ("STALLED_ON_USER"), confidence (0.95), plain English verdict, killing step, and prevention.
- Plain English quote: "The run successfully generated 6 distinct clarification questions and handed them over to the user. It then entered a 'held' state waiting for the user's input, which was never provided, causing the run to stall indefinitely."
- Revival row is still grayed out.

**What you click:** Nothing.

**What you say:** "The certificate: the run asked the user for six clarifications, got no answer, and stalled waiting. Ninety-five percent confident. The worker did not crash."

**Notes:**
- This is the moment the original verdict (WORKER_TERMINATED) is overturned by the certificate (STALLED_ON_USER).
- The text is legible; the viewer sees proof that the model is reading the actual data, not just confirming a guess.

---

## 0:52–0:59 · Revival runs (7 seconds)

**What's on screen:** 

- Certification row is collapsed to checkmark + title.
- Revival row activates with running state (timer shows ~5.8s elapsed).
- Description: "writes the resume plan."
- Header shows total elapsed time climbing toward 22.5s.

**What you click:** Nothing.

**What you say:** "The reviver writes where to restart, what work to save, and what assumptions to make to unblock."

**Notes:**
- Revival is the final sequential stage; it waits for Certification to finish.
- The timer is visible and ticking; the run is nearly done.

---

## 0:59–1:08 · Revival completes; case file visible (9 seconds)

**What's on screen:** Revival row shows:

- **Green checkmark** and "done" state.
- **Results expand** showing: `revivable: true`, `resume_at: d2dc6bb8`, skip list (empty), `unblock` assumptions, and `restart_prompt` for the orchestrator.
- Header shows "28.3s" (or similar — the full run took 28.36 seconds).
- Optional: scroll down to show "Allotment Watering Roster Setup — cause of death STALLED_ON_USER, confidence 0.95. Read the death certificate →"
- At the bottom, the statistics are visible: "92% of 39 runs stopped without reporting a failure" · "74 planned steps abandoned" · "8 of 39 had the run's own recorded cause overturned."

**What you click:** Optionally, click "Read the death certificate →" to show the full case file (a detailed scroll through the verdict chain).

**What you say:** "The run is revivable. The restart plan saves the six original questions, assumes standard defaults for the six unknowns, and posts back to the orchestrator. The entire autopsy ran in 28 seconds."

**Notes:**
- The clock and the measured timing prove the execution speed.
- The statistics at the bottom provide evidence: this is not a hypothetical — it's built on 39 real runs, 74 abandoned steps, and 8 cases where the model overturned the recorded cause.
- If you show the full case file, let the viewer read the detail: the three investigators' verdicts are visible, the survival logic is transparent.

---

## 1:08–1:15 · (Optional) Full case file detail view (7 seconds)

**If time permits, show this; if not, skip to 1:15.**

**What's on screen:** Click "Read the death certificate" or scroll to show the full case file. The page displays:

- The three investigator verdicts stacked (Timeline, Counterfactual, Competing-explanation), each showing which causes survived and which were refuted.
- Evidence bullets under each verdict.
- The killing step.
- The salvage note: "The 6 planned steps and the specific clarification questions formulated by the agent are fully preserved."

**What you click:** Scroll or page through slowly.

**What you say:** "Here's what each investigator found. Timeline says the run handed work to the user and never got it back. Counterfactual says if the user had answered, the run would have succeeded. Competing-explanation built a rival story and rejected it. All three kill the crash hypothesis."

**Notes:**
- This proves the adversarial structure. The three lenses are not rubber-stamping; they're actively destroying hypotheses.
- The evidence is visible (step IDs, state transitions, step counts).

---

## 1:15–1:45 · Context: the problem and the build (30 seconds)

**What's on screen:** Navigate to or show (via fast cuts or a narration voiceover) the context:

1. A brief mention of the graveyard tab or a screenshot showing "39 dead runs" and the statistics.
2. The agents tab, showing the six system prompts that live on the server (a fast cut showing the `prompts/` directory or the rendered agent list).
3. A terminal or Google Cloud console showing the Cloud Scheduler trigger (`*/15 * * * *`), Cloud Run services, and Firestore.

**What you click:** Navigate the tabs or show the backend console.

**What you say:** "Coroner runs six Gemini models through Vertex AI. Every fifteen minutes, Cloud Scheduler finds a run that stopped moving. The six stages run in sequence and parallel, Firestore keeps the case, and the restart plan is queued back to the orchestrator. This autopsy was live and unscripted — the timing you're seeing is real."

**Notes:**
- This is the proof of scale and automation: it's not a one-off; it's a scheduled system.
- The six agent prompts are visible (the "Agents" tab shows them).
- Keep it fast; the viewer doesn't need to understand every detail, just that there's a real backend.

---

## 1:45–3:55 · Narration: the why (2 minutes 10 seconds)

**What's on screen:** Return to the homepage or hold on a static frame of the autopsy view. The narration runs over a loop or series of still frames.

**What you say:** (Read `narration.txt` in full; see below for the exact words and pacing.)

**Notes:**
- This is the longest section and contains all the detail.
- Do not introduce new UI or new claims; just explain what was shown.
- Every number in the narration is measured or counted (39 runs, 92%, 74 abandoned steps, 8 cases overturned).

---

## 3:55–4:00 · Closing and credits (5 seconds)

**What's on screen:** The homepage or a static frame showing the Coroner headline.

**What you say:** "Coroner: the post-mortem service for silent agent failures. Six agents, one dead run, the truth."

**Notes:**
- This is the final hook; keep it short.
- Optional credit: "Gemini 3.5 Flash · Google ADK · Vertex AI · Cloud Run · Firestore."

---

## Recording checklist

- [ ] Run is `02266df1-6d2e-42be-8239-c243bd0896de` ("All six steps waiting on a human").
- [ ] Address bar is visible; URL is `coroner-295057934762.us-central1.run.app` (no query params except the run ID).
- [ ] No secret values visible (no `X-Coroner-Judge-Key`, no API keys, no bearer tokens).
- [ ] Run completes in under 50 seconds; total video is under 4:00.
- [ ] All three investigators finish before Certification starts (proof of parallelism).
- [ ] Certification overturns the recorded cause (WORKER_TERMINATED → STALLED_ON_USER).
- [ ] Revival shows the restart plan and the `unblock` assumptions.
- [ ] Statistics at the bottom are legible (92%, 74, 8 of 39).
- [ ] Narration is at a natural pace (165–180 words per minute; test by reading aloud).
- [ ] Video is uploaded to YouTube or Vimeo as **Public**.
- [ ] Video link is pasted into the Devpost form.
