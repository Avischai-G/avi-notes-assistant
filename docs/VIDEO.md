# Demo video — shot list and narration

Hard limit **4:00**. Target **3:52**. The video must be in English, must visibly show the backend
running on Google Cloud, and must be uploaded as **Public** on YouTube or Vimeo.

The first 40 seconds establish the autonomous action before showing any report. The narration is
569 words, about 3:27 at 165 words per minute; the remaining time is for pauses and live execution.
Timings are cumulative.

---

## 0:00–0:40 · The autonomous chain

**Screen — fast cuts, with timestamps legible:**

1. Cloud Scheduler console → `coroner-sweep`, ENABLED, `*/15 * * * *`. Record a scheduled attempt;
   do not click **Run now**.
2. Cloud Run logs → the matching `POST /api/sweep`, followed by the six named stages: `triage`,
   `investigator_sequence`, `investigator_counterfactual`, `investigator_alternative`, `certify`,
   `revive`.
3. Firestore → the case document written by that sweep.
4. Authenticated companion-service view → the same run ID queued for restart. Keep every key and
   authorization value off screen.

> Nothing here started with a prompt or a button. Every fifteen minutes, Cloud Scheduler posts a
> sweep to Coroner. The sweep finds a non-terminal run that has stopped moving. Google's Agent
> Development Kit delegates six model-backed stages: triage; three investigators in parallel; a
> certifier; and a reviver. Coroner persists the case in Firestore, then posts the restart plan to a
> second Cloud Run service, where the run is queued. The written plan is the last artifact in that
> chain, not the whole product.

---

## 0:40–1:06 · The problem, measured

**Screen:** graveyard at the live `*.run.app` URL, address bar visible. Put the exact metric output
from `python -m app.metrics` beside it.

> Coroner was designed against thirty-nine real runs from my own production orchestrator, used with
> the owner's permission. Those traces stay private; this published corpus is their fictional
> structural twin. Thirty-six of thirty-nine cases—ninety-two percent—were still non-terminal with
> zero recorded worker failures. Mean progress was seventeen point six nine percent. Across the
> corpus, a hundred and forty-seven steps were planned, seventy-three banked, and seventy-four
> abandoned.

---

## 1:06–1:28 · Why the prior is not the verdict

**Screen:** open *Allotment Watering Roster*. Hold on the recorded reason, regex prior, and model
certificate together.

> This case recorded that the agent's interactive CLI was stopped, so the regex prior says worker
> terminated. The certificate instead says stalled on user after considering six earlier unanswered
> questions. Across the published corpus, the certified cause differs from the regex prior in eight
> of thirty-nine cases. That is a measured model-versus-rule disagreement. It does not independently
> prove the model right in all eight.

---

## 1:28–2:18 · One autopsy, live and unedited

**Screen:** the landing page → click sample **2, All six steps waiting on a human**. Let all six
stages complete in the live view in real time — three of them visibly running at once. Do not cut,
speed up, or replace the result. Keep the `.run.app` address and the browser's Network stream
visible enough to establish that this is the deployed service.

> Here is one complete autopsy, unedited. Triage proposes two or three causes while keeping the
> deterministic prior visible. Then the sequence investigator hunts for the earliest divergence.
> The counterfactual investigator asks whether removing a proposed cause would let the run finish.
> The alternative investigator tries to build a rival explanation. Those three run in parallel.
> Certification applies the majority rule and may return undetermined. The reviver writes where to
> resume, what work to keep, and what to send back to the orchestrator. All six stages run on Gemini
> three point five Flash through Vertex AI.

---

## 2:18–2:50 · What the adversarial stage changed

**Screen:** the new case file. Show the three lens verdicts, then show the `app.metrics` output with
the metric definition in frame.

> On the thirty-nine published cases, triage proposed ninety-three hypotheses. A majority of lenses
> killed fifty-three—fifty-seven percent. A hypothesis is non-unanimous only when its three Boolean
> verdicts are not all the same. Thirteen of ninety-three met that definition, or fourteen percent.
> Across all three lens-pairs per hypothesis, twenty-six of two hundred and seventy-nine comparisons
> disagreed, or nine point three percent. Nine of the thirty-nine cases contained at least one such
> split. Those definitions and counts are in app slash metrics dot py.

---

## 2:50–3:14 · From cases to a backlog

**Screen:** Fleet report. Hold on the top recovery-manager proposal and its 12 validated run IDs.

> The fleet pass groups similar proposed preventions. For the top entry, the prescriber grouped
> twelve zombie-recovery cases under one proposed recovery-manager change. Python validates the run
> IDs, removes unknowns and duplicates, counts the group, and sorts the list. The grouping is a model
> judgment. Twelve is a checked count, not proof that the change would have saved twelve runs.

---

## 3:14–3:40 · Data boundary and offline checks

**Screen:** `app/redact.py` pattern list, then a terminal showing the eight checks passing. Keep all
eight command names legible: `test_inputs.py`, `test_corpus.py`, `test_published.py`, `app.metrics`,
`app.redact`, `app.watch`, `app.limits`, `app.resume`.

> Before Vertex AI, Coroner pattern-masks POSIX, Windows, and UNC paths; HTTP and HTTPS URLs and
> schemeless domain-path URLs; email and IPv4 addresses; JWTs, PEM private keys, database connection
> strings, AWS access-key IDs and labelled AWS secret keys, bearer tokens, common prefixed tokens,
> and long hexadecimal keys. It leaves
> ordinary prose unchanged—including names, company names, business facts, phone numbers, and
> unrecognized secret formats—so remove them first. Eight listed checks run offline without network
> or model calls.

---

## 3:40–3:57 · Category and close

**Screen:** `docs/architecture.svg`, then the graveyard headline at the live URL. Keep Cloud Run,
Firestore, Cloud Scheduler, Vertex AI, and the companion handoff visible in the diagram.

> Coroner is entered in The Taskmaster. The action is the scheduled sweep, six-stage delegation,
> Firestore write, and queued handoff; the report is what that background workflow leaves behind.
> The backend is Cloud Run, Firestore, Cloud Scheduler, and Vertex AI. Coroner: now a silent stop
> leaves a restart path.

---

## Recording and publication notes

- Record at 1920×1080 or 1512×982, 30 fps. Hide notifications and use a clean browser window.
- Capture the opening on a real quarter-hour Scheduler execution. Match the run ID and timestamps
  across Cloud Run, Firestore, and the receiver before editing.
- Keep the live autopsy unedited. Stage Two explicitly scores unedited live execution.
- Treat the displayed credentials as secrets: no header values, environment values, terminal
  history, browser extensions, or Devpost-only judge key may appear in the recording.
- Generate narration from `docs/narration.txt` if needed, then verify the final runtime is below
  4:00. Do not rely on the planned timestamps after editing.
- Upload to YouTube or Vimeo as **Public**, verify playback in a signed-out window, and place that
  public link in the Devpost submission form.
