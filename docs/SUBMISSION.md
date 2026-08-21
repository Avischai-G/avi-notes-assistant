# Devpost submission — draft for Avi's approval

**Nothing here has been submitted or registered.** This is the exact text that would go into the
form, so you can read it before anything goes out.

---

## Project name

**Coroner**

## Tagline (Devpost "elevator pitch", 200 char max)

> Your agents don't crash. They ghost you. Coroner autopsies the runs that stopped without a word,
> tells you what killed them, and writes the plan to restart them.

## Category

**The Fortified Enterprise Fleet** — the track about making a fleet of agents survivable.

## Hosted project URL

https://coroner-295057934762.us-central1.run.app

## Repository

*(to be created — needs your yes before anything is pushed)*

---

## About the project

### Inspiration

A multi-agent run that fails loudly is easy: you get a stack trace, you fix it. The expensive ones
are the runs that simply stop. The board still looks alive, no error was ever raised, and three days
later somebody notices nothing has moved.

I had 39 of them sitting on disk — real dead runs from a production multi-agent orchestrator. So
before designing anything I read them. **Thirty-six of the thirty-nine had stopped without ever
reporting a failure.** On average they had banked 18% of their planned work before going quiet;
across the fleet, 74 of 147 planned steps were simply abandoned.

The thing that decided the whole design was smaller. One run recorded its stop reason as *"The
agent's interactive CLI was stopped."* A rule that matches on that string calls it a dead worker
process and moves on. It is wrong. The run had asked the human six clarifying questions hours
earlier and had been sitting on them ever since; the CLI closing was the *consequence* of a run that
was already dead, not the cause. Across the corpus, the recorded reason was misleading on 8 of 39
runs.

You cannot fix that with better regexes. It needs something that argues.

### What it does

Give Coroner the trace a dead run left behind. It returns a case file:

- **Cause of death**, from a nine-cause taxonomy read off the real corpus rather than invented.
- **The killing step** — which step was in flight, what it was told to do, what it reported back.
- **What it cost** — how much of the planned work was thrown away.
- **The prevention** — one concrete change to the orchestrator, specific enough to be a ticket.
- **A revival kit** — where to restart, which steps not to redo, the assumption to proceed under,
  and the exact prompt to hand back to the orchestrator.

Point it at a whole graveyard and it does the thing a single autopsy cannot: it collapses 39
separate preventions into the ranked list of changes that would have saved the most runs.

> **12 of 39 runs** would have been saved by one change to the recovery manager.

And because 92% of dead runs never announce themselves, Coroner does not wait to be asked. A
Cloud Scheduler job sweeps every fifteen minutes; any run that is still in a non-terminal state and
has not moved for thirty minutes is presumed dead and autopsied unprompted.

### How I built it

Six ADK agents, wired as `SequentialAgent → ParallelAgent(3) → LlmAgent → LlmAgent`, all on
`gemini-3.5-flash` via Vertex AI.

1. **triage** proposes 2–3 candidate causes. It is shown the rule-based guess and explicitly told
   that guess is fooled whenever the recorded reason describes the symptom rather than the cause.
2. **three investigators, in parallel, each told to destroy the hypotheses** — not to check them.
   Crucially they are given *different jobs*, because three identical skeptics agree with each
   other: one attacks the timeline and looks for the earliest divergence, one runs the
   counterfactual (remove this cause — would the run have finished?), one tries to build a rival
   explanation that fits every observation at least as well.
3. **certify** issues the death certificate. A cause survives only a majority of lenses; if none
   survives the answer is UNDETERMINED, and the agent is told not to invent one to avoid saying so.
4. **revive** writes the resume plan.

Three design decisions I would defend:

**The evidence layer never calls a model.** Statuses, retry counts, dependency graphs, which step
was in flight, how much work was banked — all counted in Python and handed to the agents as ground
truth they are forbidden to recompute. A model allowed to count will eventually count wrong, and a
post-mortem that gets its own arithmetic wrong is worse than none.

**Diversity, not redundancy, in the adversarial stage.** Measured over the corpus: 56% of proposed
hypotheses were killed by a majority of lenses, and the three lenses disagreed with each other on
60% of hypotheses. If they had been three copies of the same skeptic that number would be near zero
and the stage would be theatre.

**The published corpus is the private one with the names changed.** The 39 traces are somebody's
real work and cannot ship. So every structural field is copied byte-for-byte — statuses, dependency
graph, retry counts, stop reasons, the completed-step ledger — and only the project content is
regenerated as unrelated fiction. A test asserts the twin still produces an identical cause
distribution and identical per-run progress; a second test asserts that none of the 64,674 six-word
phrases in the private corpus survives into the published one. Separately, a redactor replaces
paths, URLs, keys and emails with stable typed placeholders before the first model call, so pointing
Coroner at your graveyard does not mean shipping your prompts to anyone.

**Stack:** Gemini 3.5 Flash · Google ADK 2.7 · Vertex AI · Cloud Run · Firestore · Cloud Scheduler ·
FastAPI. No frontend framework and no build step — the UI is three files served from the container.

### Challenges

The recorded reason lying is the interesting one, and it is why the middle stage exists at all. The
subtler problem was making adversarial review mean something: my first version ran three identical
"try to refute this" agents and they agreed with each other on everything, which looks rigorous and
proves nothing. Giving each one a different lens is what turned the stage from decoration into a
filter that kills 56% of hypotheses.

The other real one was privacy. The dataset that makes this project credible is exactly the dataset
that cannot be published. Structural cloning — with tests that prove both halves of the claim —
was the way out.

### Accomplishments

The corpus is real, and the finding is not one I expected: agent runs mostly do not fail, they
stall, and they stall after doing most of the planning and almost none of the work. On 8 of 39 runs
the agents overruled a rule that would have confidently told you the wrong thing.

### What I learned

That "adversarial verification" is a claim you have to measure, not assert. And that the useful
output of a post-mortem system is not the post-mortem — it is the one line at the top of the fleet
report that says which single change would have saved the most runs.

### What's next

Adapters for other orchestrators (`app/traces.py` is the seam — one function per vendor), and
closing the loop: handing the revival kit back to the orchestrator automatically instead of putting
a copy button next to it.

---

## Requirement check

| Required | This project |
|---|---|
| Gemini 3.5 or newer | `gemini-3.5-flash` on Vertex AI (location `global`) |
| A Google agent framework | Google ADK 2.7 — `SequentialAgent`, `ParallelAgent`, `LlmAgent`, `Runner`, typed `output_schema` |
| A Google Cloud infrastructure service | Cloud Run + Firestore (+ Cloud Scheduler) |
| Newly created in the submission period | First commit 2026-08-20 |
| Hosted URL | https://coroner-295057934762.us-central1.run.app |
| README with spin-up instructions | Yes |
| Architecture diagram | `docs/architecture.svg` |
| Demo video ≤ 4 min, backend visibly on Google Cloud | **Not recorded yet** |
