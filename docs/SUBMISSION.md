# Devpost submission — draft for Avi's approval

**Nothing here has been submitted or registered.** This is the exact text that would go into the
form, so you can read it before anything goes out.

---

## Project name

**Coroner**

## Tagline (Devpost "elevator pitch", 200 char max)

> Your agents don't crash. They ghost you. Coroner finds silent stops, runs a six-agent autopsy,
> persists the case, and queues a restart plan without waiting for an operator.

## Category

**The Taskmaster.** The first draft named The Fortified Enterprise Fleet. Coroner does not implement
that category's defining registry/discovery, authenticated identity, durable multi-week context,
compliance/data-sovereignty, or OpenTelemetry outcomes. What it demonstrates is autonomous
background execution of a messy operational workflow. See
[`RULES-FINDINGS.md`](RULES-FINDINGS.md) for the controlling rule text and category comparison.

## Hosted project URL

https://coroner-295057934762.us-central1.run.app

Companion service (the stand-in orchestrator that receives the restarts):
https://coroner-orchestrator-295057934762.us-central1.run.app

## Judge access

The public model-backed endpoints are rate-limited because they bill a private individual. Judges
receive a separate key in the Devpost testing instructions. Send that value in the
`X-Coroner-Judge-Key` request header; a correctly configured key bypasses the public rate gate. No
key value belongs in the repository, this draft, or the demo video.

## Repository

*(to be created — needs your yes before anything is pushed)*

---

## About the project

### Inspiration

A multi-agent run that fails loudly is easy: you get a stack trace, you fix it. The expensive ones
are the runs that simply stop. The board still looks alive, no error was ever raised, and three days
later somebody notices nothing has moved.

I had 39 of them sitting on disk: real runs from my own production multi-agent orchestrator, used
with the owner's permission. The private traces do not ship; the published corpus is their
fictional structural twin. `app/metrics.py` measures the published case files: **36 of 39 (92%)**
were classified as silent because they were still non-terminal and recorded zero worker failures.
Mean progress was **17.69%**. Across the corpus, **147 steps were planned, 73 banked, and 74
abandoned**.

The thing that decided the design was smaller. One run recorded *"The agent's interactive CLI was
stopped."* The deterministic regex prior classifies that text as `WORKER_TERMINATED`. The model
certificate instead selects `STALLED_ON_USER` after considering six earlier unanswered questions.
Across the published corpus, the certified cause differs from the regex prior in **8 of 39** cases.
That is a measured model-vs-rule disagreement, not an independent label proving the model right in
all eight.

That gap is why Coroner keeps the prior but makes it face three different investigations.

### What it does

Coroner acts before it writes. Every fifteen minutes Cloud Scheduler triggers `/api/sweep`. The
sweep finds non-terminal runs that have not moved for thirty minutes. Six agent stages investigate
each new stale run; Coroner writes the case file to Firestore and POSTs the restart plan to an
authenticated second service, where it becomes a queued restart. No operator starts that chain.

The persisted case file contains:

- **Cause of death**, from eight specific cause labels plus `UNDETERMINED`.
- **The killing step** — which step was in flight, what it was told to do, what it reported back.
- **What it cost** — how much of the planned work was thrown away.
- **The prevention** — one concrete change to the orchestrator, specific enough to be a ticket.
- **A revival kit** — where to restart, which steps not to redo, the assumption to proceed under,
  and the exact prompt to hand back to the orchestrator.

Point it at a whole graveyard and the prescriber groups similar proposed preventions. Python then
validates the returned run IDs, removes unknown and duplicate IDs, counts them, and orders the
groups.

> The prescriber grouped **12 zombie-recovery cases** under one proposed recovery-manager change.

The 12 is a deterministic count of validated run IDs. The grouping and remedy are model output;
there is no counterfactual experiment showing that the change would have saved all 12 runs.

Then it hands the restart back. Set a webhook and Coroner POSTs the resume plan straight to your
orchestrator; a stand-in receiver is deployed next to the demo so you can watch a dead run land in a
restart queue rather than take my word for it. If delivery fails, it says so — a restart you believe
happened and did not is worse than none.

Put together: the scheduled trigger, sweep, six-stage delegation, Firestore write, and authenticated
handoff are the product action. The written restart plan is the final artifact of that chain.

### How I built it

Six ADK agents, wired as `SequentialAgent → ParallelAgent(3) → LlmAgent → LlmAgent`, all on
`gemini-3.5-flash` via Vertex AI.

1. **triage** proposes 2–3 candidate causes. It is shown the rule-based guess and explicitly told
   that guess is fooled whenever the recorded reason describes the symptom rather than the cause.
2. **three investigators, in parallel, each told to destroy the hypotheses** — not to check them.
   They are given different jobs: one attacks the timeline and looks for the earliest divergence,
   one runs the counterfactual (remove this cause — would the run have finished?), and one tries to
   build a rival explanation that fits every observation at least as well.
3. **certify** issues the death certificate. A cause survives only a majority of lenses; if none
   survives the answer is UNDETERMINED, and the agent is told not to invent one to avoid saying so.
4. **revive** writes the resume plan.

Three design decisions I would defend:

**The evidence layer never calls a model.** Statuses, retry counts, dependency graphs, which step
was in flight, and how much work was banked are computed in Python. The agents receive those
deterministic observations and are told not to recompute them.

**Diversity, not redundancy, in the adversarial stage.** On the published cases, triage proposed
**93 hypotheses** and a majority of lenses killed **53 (57%)**. A hypothesis is non-unanimous when
the three Boolean survival verdicts are not all equal; **13 of 93 (14.0%)** met that definition.
That produced **26 disagreements in 279 pairwise comparisons (9.3%)**, and **9 of 39 cases** had at
least one non-unanimous hypothesis. `app/metrics.py` defines and computes each denominator.

**The published corpus is a checked structural twin, not a byte-for-byte copy.** `test_corpus.py`
compares the deterministic rule prior, per-run progress, step statuses, dependency graph, and retry
counts. Stop reasons and prose may be rewritten, and model-generated certificates may differ.
`test_published.py` rejects five banned strings and any verbatim six-word phrase shared with the
private free-text fields; the test prints the current number of private phrases instead of freezing
a count here.

**Redaction has a defined limit.** Before Vertex AI, `app/redact.py` pattern-masks POSIX, Windows,
and UNC paths; HTTP(S) and schemeless domain/path URLs; emails and IPv4 addresses; JWTs, PEM private
keys, database connection strings, AWS access-key IDs and labelled AWS secret keys, bearer tokens,
common prefixed tokens, and long hexadecimal keys. Ordinary prose is not anonymized: names, company
names, business facts, phone numbers, and unrecognized secret formats are sent to Vertex AI
unchanged. A user must remove that
material before uploading a trace.

**Stack:** Gemini 3.5 Flash · Google ADK 2.7 · Vertex AI · Cloud Run · Firestore · Cloud Scheduler ·
FastAPI. No frontend framework and no build step — the UI is three files served from the container.

### Challenges

The recorded reason is useful but not conclusive, which is why the middle stage exists. The subtler
problem was making adversarial review mean something. Giving each investigator a different lens
creates distinct tests of sequence, causality, and alternative explanation; the measured result is
that a majority rejects 53 of 93 published hypotheses, while 13 receive a split verdict.

The other real one was privacy. The dataset that makes this project credible is exactly the dataset
that cannot be published. Structural cloning, with explicit checks for selected structural fields
and six-word verbatim overlap, was the way out.

### Accomplishments

The source traces are real, owner-authorized production runs, and their structural twin preserves
the observed shape: 36 of 39 are silent under Coroner's deterministic definition, and only 73 of
147 planned steps were banked. In 8 of 39 published cases, the model certificate differs from the
regex prior; that disagreement is visible instead of silently replacing the prior.

### What I learned

That "adversarial verification" is a claim you have to define and measure. And that a post-mortem
workflow is useful when it persists the diagnosis, hands back a restart, and turns repeated proposed
fixes into a counted backlog—not when it merely renders a report.

### What's next

Adapters for other orchestrators (`app/traces.py` is the seam—one function per vendor), production
handoff integrations beyond the stand-in receiver, and independently labelled outcomes for testing
whether model-vs-rule disagreements are actually improvements.

---

## Offline verification

All eight checks run with no network and no model calls:

1. `test_inputs.py` — malformed input, request bounds, prompt boundary, UI and handoff regressions.
2. `test_corpus.py` — taxonomy coverage and the twin fields it explicitly compares.
3. `test_published.py` — banned strings and verbatim six-word private/public overlap.
4. `python -m app.metrics` — metric-definition fixture and corpus measurements.
5. `python -m app.redact` — every documented pattern class and stable placeholders.
6. `python -m app.watch` — stale/fresh/terminal watcher behavior.
7. `python -m app.limits` — per-caller and per-instance refusal/refill behavior.
8. `python -m app.resume` — authenticated delivery and explicit failure results.

The full `test_published.py` and `app.metrics` commands require maintainer-local corpus directories;
they do not fetch those inputs. The checked published metrics are 39 cases, 93 proposed
hypotheses, 53 majority-killed hypotheses, 13 non-unanimous hypotheses, 26/279 pairwise lens
disagreements, 9 cases with a split, 8 certificate/prior disagreements, 36 silent stops, 17.6945%
mean progress, and 147/73/74 steps planned/banked/abandoned.

---

## Requirement check

| Required | This project |
|---|---|
| Gemini 3.5 or newer | `gemini-3.5-flash` on Vertex AI (location `global`) |
| A Google agent framework | Google ADK 2.7 — `SequentialAgent`, `ParallelAgent`, `LlmAgent`, `Runner`, typed `output_schema` |
| A Google Cloud infrastructure service | Cloud Run + Firestore (+ Cloud Scheduler) |
| Newly created in the submission period | Root commit dated 2026-08-21 |
| Hosted URL | https://coroner-295057934762.us-central1.run.app |
| README with spin-up instructions | Yes |
| Architecture diagram | `docs/architecture.svg` |
| Demo video ≤ 4 min, backend visibly on Google Cloud | **Not recorded yet** |
