# Demo video — shot list and narration

Hard limit **4:00**. Target **3:30**. Must be in English and must visibly show the backend running
on Google Cloud.

Narration below is ~520 words ≈ 3:25 at a normal pace. Timings are cumulative.

---

## 0:00–0:22 · The problem

**Screen:** the graveyard view at the live `*.run.app` URL, address bar visible. Slow scroll.

> Agent runs don't usually crash. They stall.
>
> These are thirty-nine real dead runs from a production multi-agent orchestrator. Thirty-six of
> them — ninety-two percent — stopped without ever reporting a failure. No error, no alert. The
> board still looked alive. On average they'd banked eighteen percent of their planned work before
> going quiet, which means seventy-four of a hundred and forty-seven planned steps were simply
> abandoned.

---

## 0:22–0:55 · Why rules aren't enough

**Screen:** click into the `OVERRULED` case — *Allotment Watering Roster*. Hold on the certificate
rows so "Recorded reason" and "Rules said" are both legible.

> Here's why this needs agents and not regexes.
>
> This run recorded its own cause of death as "the agent's interactive CLI was stopped". A
> string-matcher reads that and calls it a dead worker process. It's wrong.
>
> The run had asked the human six clarifying questions hours earlier and had been sitting on them
> ever since. The CLI closing was the consequence of a run that was already dead — not the cause.
> Across this corpus the recorded reason was misleading on eight of the thirty-nine runs.

---

## 0:55–1:45 · The autopsy, live

**Screen:** New autopsy → "Load a real dead run" → "Begin autopsy". Let the six pipeline nodes light
up in real time. Do not cut. It takes about thirty-five seconds.

> So Coroner argues about it. Six agents, built with Google's Agent Development Kit, running on
> Gemini 3.5 through Vertex AI.
>
> Triage proposes two or three candidate causes — and it's explicitly told the rule-based guess is
> fooled whenever the recorded reason describes the symptom instead of the cause.
>
> Then three investigators run in parallel, and every one of them is told to *destroy* those
> hypotheses, not check them. The important part is that they're given different jobs. One attacks
> the timeline and hunts for the earliest divergence. One runs the counterfactual — remove this
> cause, would the run have finished? One tries to build a rival explanation that fits every
> observation just as well.
>
> Three identical skeptics would agree with each other. These don't: measured across the corpus,
> they disagree on sixty percent of hypotheses, and they kill fifty-six percent of everything triage
> proposes.

---

## 1:45–2:20 · The certificate and the revival kit

**Screen:** the case file it just produced. Scroll through the three lenses — pause where one says
SURVIVED and the others say REFUTED — then down to the revival kit.

> Certification takes a majority vote. If nothing survives, the answer is "undetermined" — it is
> told not to invent a cause to avoid saying so.
>
> And then it doesn't stop at a diagnosis. The revival kit says where to restart, which steps not to
> redo, what assumption to proceed under instead of waiting on a human who never answered, and the
> exact prompt to hand back to the orchestrator.

---

## 2:20–2:50 · The fleet report

**Screen:** Fleet report.

> One autopsy is mildly interesting. Thirty-nine is an engineering backlog.
>
> Every certificate proposed a fix for its own run. Most are the same handful of fixes in different
> words, so a final agent collapses them and ranks them by deaths prevented. One change to the
> recovery manager would have saved twelve of thirty-nine runs.
>
> Every number on this page is counted in Python and handed to the model as ground truth. It ranks.
> It never counts.

---

## 2:50–3:15 · It doesn't wait to be asked

**Screen:** the watcher line on the graveyard ("Watching 39 runs · last swept … "), then the
Cloud Scheduler job in the console.

> Ninety-two percent of these runs never announced they'd died — so a post-mortem service you have
> to *ask* only solves half the problem. Cloud Scheduler hits Coroner every fifteen minutes. Any run
> still in a non-terminal state that hasn't moved in thirty minutes is presumed dead and autopsied
> without anyone asking.

---

## 3:15–3:35 · Backend on Google Cloud  *(required shot)*

**Screen — must all be visible:**
1. Cloud Run console → service `coroner`, revision serving 100% of traffic, region `us-central1`.
2. Cloud Run **Logs** tab with the requests from the live autopsy just performed.
3. Firestore console → database `coroner` → `cases` collection, 39 documents.
4. Cloud Scheduler console → job `coroner-sweep`, ENABLED, `*/15 * * * *`.

> The whole backend runs on Google Cloud: the service on Cloud Run, the case files in Firestore, the
> watcher on Cloud Scheduler, and every one of those six agents on Gemini 3.5 through Vertex AI.

---

## 3:35–3:45 · Close

**Screen:** back to the graveyard, headline figures visible.

> Coroner. Your agents don't crash — they ghost you. Now you know what killed them, and how to bring
> them back.

---

## Recording notes

- Record at 1920×1080 or 1512×982 (native), 30fps. `screencapture -v -V 260 -R0,0,1512,982 out.mov`
  captures the display; keep the recording in one take per section and stitch with ffmpeg.
- Narration can be produced without a microphone:
  `say -v Ava -r 165 -o narration.aiff -f docs/narration.txt`
  then `ffmpeg -i out.mov -i narration.aiff -c:v copy -shortest final.mp4`.
- Hide notifications (Do Not Disturb) and use a clean browser window with no bookmarks bar.
- The live autopsy must not be cut. "Unedited live execution proof" is explicitly scored.
- Upload to YouTube as **public** (unlisted is not accepted by the rules).
