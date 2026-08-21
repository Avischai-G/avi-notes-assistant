# Demo video — shot list and narration

**Hard limit 4:00.** Budget for live execution variance: the autopsy measured 28.4 seconds on one run, 47.4 seconds on deployment. Every beat below is triggered by a visual event, not a clock time, so the script remains valid across the full range.

The video must be in English, must visibly show the hosted service on Google Cloud, and must be uploaded as **Public** on YouTube or Vimeo. Address bar is visible; no secret values on screen.

**Every beat must have visible motion.** No static frames. The narration is cut to fit the video, not the other way around.

---

## 0:00–0:30 · Hook and problem (approximately 30 seconds)

**Visual narrative:**
1. **Fade in on the Coroner homepage.** Address bar shows `coroner-295057934762.us-central1.run.app`. Headline: "Six agents cut open one dead agent run and tell you what killed it."
2. **Read the three sample-run cards aloud:** "Pick a dead run. It is autopsied live, in about thirty seconds." The three cards are visible.
3. **Click card #2: "All six steps waiting on a human"** (run `02266df1-6d2e-42be-8239-c243bd0896de`).
4. **Brief voiceover while the page transitions:** "An agent run that stops and says nothing is invisible. Nobody gets woken up. Three days later somebody notices the timestamp hasn't changed."

**Narration (voiceover):**
"Agent runs don't crash the way you'd expect. They ghost you. No error. No log. Just silence. Coroner is the post-mortem service for that problem."

**Duration:** ~25–35s depending on page load.

---

## 0:30–1:35 · Live autopsy streaming (approximately 65 seconds)

**Visual narrative — watch the terminal view unfold as it runs, with no cuts or interruptions. The autopsy is the performance.**

1. **The terminal-style view materializes.** Header: "Triage is running". Elapsed timer visible and ticking.
2. **Triage completes (around 6 seconds in).** Green checkmark. Results expand showing three candidate causes with confidence scores.
3. **Immediately, three investigator rows light up and start in parallel.** Timeline, Counterfactual, Competing-explanation. Timers ticking on the right for each.
   - **Voiceover:** "Triage proposes causes. Then three investigators attack them at once, each from a different angle."
4. **Investigators finish one by one** (next ~10 seconds). Each shows a green checkmark as it completes. Results expand. Evidence becomes visible.
   - **Voiceover:** "Timeline looks for when the run switched from working to stalled. Counterfactual asks: if we removed this cause, would it finish? Competing-explanation builds a rival story."
5. **Certification row activates** (around 16 seconds in). Timer ticks.
6. **Certification completes** (around 22 seconds in). Green checkmark. Results expand: final cause, confidence (0.95), plain-English verdict.
   - **Key moment — voiceover:** "The run's own record said the worker crashed. The certificate says it was waiting on the user. The model overturned the prior."
7. **Revival row activates** (around 22.5 seconds in). Timer ticks.
8. **Revival completes** (around 28–47 seconds depending on deployment). Green checkmark. Results expand: `revivable: true`, `resume_at: [step ID]`, `unblock` assumptions, `restart_prompt`.
   - **Voiceover:** "The reviver writes where to restart, what work to save, and the assumptions to proceed under."

**Critical instruction:** Do not interrupt this section with cuts or transitions. It is one continuous stream. The timers and checkmarks are the visual narration. Keep the camera on the page. Scroll only if needed to show new sections appearing.

**Duration:** 47–65 seconds (depends on actual run timing; wait for revival to complete, do not cut early).

---

## 1:35–2:00 · Why this matters: the overturned verdict (approximately 25 seconds)

**Visual narrative:**

1. **From the autopsy view, scroll down slightly to show the full case file.** Visible now: the three investigator verdicts stacked, each showing SURVIVED and REFUTED.
2. **Highlight or read aloud:** All three investigators independently killed the WORKER_TERMINATED hypothesis. STALLED_ON_USER survived all three.
3. **Scroll or transition to show the statistics at the bottom of the page:** "92% of 39 runs stopped without reporting a failure." "74 planned steps abandoned." "8 of 39 had the run's own recorded cause overturned."
4. **Voiceover:** "Across 39 real runs from production, the model and the rules disagree in 8 cases. That is proof the adversarial structure works."

**Duration:** ~20–30s (read the evidence at a pace the viewer can follow).

---

## 2:00–2:30 · How it works: the six agents (approximately 30 seconds)

**Visual narrative:**

1. **Click or navigate to the "The six agents" tab.** The page shows the six system prompts rendered from files. Triage, Timeline, Counterfactual, Competing-explanation, Certification, Revival.
2. **Scroll through the first two or three agents' prompts** so the viewer sees they are real text, not marketing copy. Each has a clear job.
3. **Voiceover:** "Six Gemini models. Each one has a job. Triage proposes. Three investigators destroy hypotheses. Certifier reads the votes. Reviver writes the restart."
4. **Optional:** Show the "Collaborative Partner" or "Fortified Enterprise Fleet" tabs to demonstrate the product is being judged against multiple categories.

**Duration:** ~25–35s (scroll at a readable pace).

---

## 2:30–3:05 · Cloud deployment proof (approximately 35 seconds)

**Visual narrative:**

1. **Open the Google Cloud Console in a new tab.** Navigate to **Cloud Scheduler**.
2. **Show the `coroner-sweep` job.** Visible must be:
   - Job name: `coroner-sweep`
   - Schedule: `*/15 * * * *` (every 15 minutes)
   - Status: ENABLED (green checkmark)
   - **Do NOT show:** any secrets, API keys, billing information, full project ID if avoidable.
3. **Click "View logs" or navigate to Cloud Run logs.** Show the recent POST `/api/sweep` entry. Scroll down slightly to show the six named stages (triage, investigator_sequence, investigator_counterfactual, investigator_alternative, certify, revive) in the logs.
4. **Voiceover:** "Every fifteen minutes, Cloud Scheduler finds a run that stopped moving. The six-stage autopsy runs unsupervised. Firestore keeps the case. The restart plan is queued back."
5. **Brief shot of Firestore:** Navigate to Firestore and show the `coroner` database with a case document. Show the `title`, `cause`, `confidence` fields. Do NOT show secrets or connection strings.

**Duration:** ~30–40s (slow enough to read the labels, fast enough to stay engaging).

**Critical:** Keep every value and identifier visible. The judge must be able to see that this is deployed, scheduled, and real. No blurred screens.

---

## 3:05–3:35 · The corpus and the fleet report (approximately 30 seconds)

**Visual narrative:**

1. **Navigate to the "Fleet report" tab** or show the graveyard view with statistics prominent.
2. **Read aloud or display:**
   - "92% of 39 runs stopped without reporting a failure."
   - "147 steps planned, 73 banked, 74 abandoned across the corpus."
   - "6 ranked prevention proposals."
   - "8 of 39 cases where the model verdict differs from the recorded cause."
3. **Scroll through the fleet report to show the top 2–3 prevention proposals.** Each shows a grouped set of run IDs, a proposed change, and the count of cases affected. For example: "Recovery manager: 12 cases."
4. **Voiceover:** "The prescriber groups similar preventions. Twelve cases point to one recovery-manager fix. The twelve is a real count of run IDs. The remedy is a model judgment — not proof it would have saved all twelve."

**Duration:** ~25–35s.

---

## 3:35–4:00 · Close (approximately 25 seconds)

**Visual narrative:**

1. **Return to or show the homepage one more time.**
2. **Read the headline:** "Six agents cut open one dead agent run and tell you what killed it."
3. **Closing voiceover:** "Coroner: six autonomous agents, one dead run, the truth. Now you can see what killed yours."
4. **Fade or hold on the Coroner logo/header.**

**Duration:** ~20–25s.

---

## Production notes

### Pacing the narration

Narration word count is ~230 words, timed to be spoken at 160–180 wpm with natural pauses. That fits comfortably into the beats above with room for silence and visual focus.

### Handling variance

If the autopsy takes 47 seconds instead of 28 seconds:
- The live autopsy section (0:30–1:35) expands. Wait for all stages to complete; do not cut.
- Tighten the subsequent beats slightly (Fleet report, proof of deployment) to hold the 4:00 limit.
- The narration remains the same; you simply pause longer on visuals.

### Secrets and identifiers

✓ Address bar (URL) must be visible.
✓ Run IDs, case titles, step IDs are public.
✓ Log output (stages, timestamps) is safe to show.
✗ Do NOT show: `X-Coroner-Judge-Key`, API keys, database connection strings, full project ID with billing account, credential files.
✗ Do NOT show: personal names or identifying information from the case run prompts.

### Recording checklist

- [ ] Run is `02266df1-6d2e-42be-8239-c243bd0896de` ("All six steps waiting on a human").
- [ ] Run title matches API: "Allotment Watering Roster **Setup**" (not "System").
- [ ] Every beat has motion (no static frames for more than 2 seconds).
- [ ] Triage completes before investigators start (proof of sequencing).
- [ ] All three investigators show timers running in parallel.
- [ ] Investigators complete before Certification starts (proof of join).
- [ ] Certification shows 0.95 confidence in STALLED_ON_USER (overturns prior).
- [ ] Revival shows `revivable: true` and restart assumptions.
- [ ] Statistics are legible (92%, 74, 8 of 39).
- [ ] Cloud Scheduler job visible: `coroner-sweep`, `*/15 * * * *`, ENABLED.
- [ ] Cloud Run logs show the six named stages.
- [ ] No secrets visible (no judge key, no billing, no API key).
- [ ] Total runtime ≤ 4:00.
- [ ] Video is uploaded to YouTube or Vimeo as **Public**.
- [ ] Video link is pasted into the Devpost form.
