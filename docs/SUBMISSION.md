# Devpost submission

**This submission has not been registered or submitted.** This is the exact text for the Devpost form, provided for review.

---

## Project name

**Coroner**

## Tagline (200 character limit)

Your agents don't crash. They ghost you. Coroner finds silent stops, runs a six-agent autopsy, persists the case, and queues a restart plan without waiting for an operator.

## Category

**The Taskmaster.** The defining rule for The Taskmaster is autonomous action without human operator intervention — the system must execute end-to-end triggered work, delegate that work, and hand results back to the requesting system. Coroner satisfies that requirement: Cloud Scheduler triggers a sweep, six agent stages execute the autopsy, Firestore persists the case file, and the restart plan is POSTed to an authenticated orchestrator service without waiting for an approval.

## Hosted project URL

https://coroner-295057934762.us-central1.run.app

Companion service (stand-in orchestrator): https://coroner-orchestrator-295057934762.us-central1.run.app

Judge access: send the provided `X-Coroner-Judge-Key` header value with requests to bypass public rate limits.

## Repository

To be created after approval.

---

## About the project

### Inspiration

The expensive agent failures are not the loud ones. A loud failure gives you a stack trace, you fix it, and you move on. The silent ones are the killers. The run stops moving. The board still looks alive. No error was ever raised. Three days later somebody notices the timestamp hasn't changed.

I had 39 of them on disk: real runs from my own production multi-agent orchestrator, used with the owner's permission. The private traces remain private; the published corpus is their fictional structural twin. These 39 cases form the evidence base for Coroner's design.

**The measured problem:**

- **92% of 39 runs (36 cases)** stopped without recording a failure. They were silent.
- **Mean progress: 17.69%.** The runs got partway through and froze.
- **147 steps planned, 73 banked, 74 abandoned** across the full corpus. That's 74 units of work thrown away mid-flight with no trace of why.

The insight came from one specific case. The run recorded: "The agent's interactive CLI was stopped." A deterministic regex prior classifies that as `WORKER_TERMINATED` — the worker crashed. But the run had actually asked the user for six clarifications and was holding, waiting for answers. The recorded cause was wrong.

Across the published 39 cases, the deterministic regex prior and a model-based autopsy disagree in **8 of 39 cases (20%).**  That gap is why Coroner doesn't just apply the regex; it keeps the prior *and* runs three adversarial investigators to challenge it.

### What it does

Coroner is fully autonomous. Every fifteen minutes, Cloud Scheduler triggers `/api/sweep`. The sweep finds non-terminal runs that have not progressed in 30 minutes and are presumed dead.

Six Gemini 3.5 Flash agents (via Vertex AI) then investigate each new case in a staged pipeline:

1. **Triage:** Proposes 2–3 candidate causes and confidence scores. Keeps the deterministic prior visible.
2. **Three investigators run in parallel** (the next 3–10 seconds):
   - **Timeline investigator:** Finds the earliest divergence in the run's state transitions.
   - **Counterfactual investigator:** Tests each hypothesis with a what-if premise: "If we removed this cause, would the run finish?"
   - **Competing-explanation investigator:** Builds an alternative narrative and grades how well it explains the evidence.
3. **Certification:** Reads the three verdicts, applies majority rule, issues the death certificate with a single final cause and confidence score.
4. **Revival:** Writes a restart plan containing:
   - Where to resume execution
   - Which steps to skip
   - What assumptions to make to unblock
   - The exact prompt to hand back to the orchestrator

The case file is persisted to Firestore. The restart plan is POSTed to an authenticated second Cloud Run service where it enters a restart queue.

**On the 39-case corpus:**

- The three investigators identify which causes survive all three lenses (not killed by any investigator).
- **8 of 39 cases have a certified cause that differs from the regex prior.** This is measured disagreement, not proof the model is correct in all 8; it shows the adversarial structure catches conflicts that rule-based routing would miss.
- **74 abandoned steps** measures the wreckage left behind; it is a measure of complexity, not a proof of recovery success.
- **`wasted_effort` and `revivable` values** are the model's recorded judgment in each case file, not independently verified outcomes.

The revival fleet groups similar preventions. For the top entry, the system identified 12 cases proposing a recovery-manager change. The 12 is a deterministic count of validated run IDs. The grouping and remedy are model judgments; there is no independent experiment showing the change would have saved all 12.

### How I built it

**Backend:**
- Cloud Run (two services): Coroner autopsy service and companion orchestrator stand-in for restart delivery
- Firestore: native database named `coroner`, stores case files and run metadata
- Cloud Scheduler: triggers `/api/sweep` every 15 minutes (`*/15 * * * *`)
- Vertex AI: delegates six named stages to Gemini 3.5 Flash
- Six agent prompts loaded from files at runtime (`prompts/*.md`)

**Frontend:**
- Interactive autopsy UI built with streaming SSE
- CLI-style terminal view showing stage progression, elapsed time per agent, and result expansion
- Tabs: The six agents (shows the six system prompts), Graveyard (all 39 cases), Fleet report (grouped preventions), and category rules (Taskmaster, Collaborative Partner, Fortified Enterprise Fleet)
- Public endpoint demonstrates live execution; judge key bypasses rate limits

**Data:**
- 39 published cases (fictional structural twins of real runs)
- Metrics: step counts, cause distributions, investigator agreement, prior-vs-verdict mismatches

### Challenges I ran into

**Designing the autopsy as a testable claim:** Silent runs leave almost no signal. A run that stops without an error and without changing state is indistinguishable from "the run died" vs. "the run is waiting." The only way to test was to build an orchestrator corpus, then design agents that actively *destroy* hypotheses rather than confirm them.

**Making the model output trustworthy:** LLMs are good at storytelling. I needed to force disagreement so wrong stories don't survive. Three independent lenses, each told to refute the others, each with a different axis of attack.

**Measuring against reality:** All numbers in this submission come from `app/metrics.py`, which counts the published cases, not invented figures. The 92%, 74, 8-of-39, and 12-case groupings are deterministic measurements, not model confidence scores.

### Accomplishments that I'm proud of

- **A working definition of "silent failure":** not "crashed" but "stalled non-terminal with zero recorded errors."
- **Measured evidence that adversarial design works:** 8 cases where the model verdict diverges from the regex prior, showing the three-lens structure catches false positives the rules would confirm.
- **An unattended pipeline that scales:** The sweep runs every 15 minutes; six stages delegate to Gemini; results persist; the restart is queued. No operator involvement.
- **Honest uncertainty in the output:** The case file preserves the prior cause, shows the three lens verdicts with evidence, and clearly labels which judgments are model-based (revival assumptions, prevention proposals) vs. deterministic counts (step totals, run IDs).

### What I learned

1. **Adversarial design is not just for security.** It's a model debugging technique. When three independent systems try to refute the same hypothesis from different angles, the ones that survive are more trustworthy.
2. **The corpus matters more than the model.** I could have used GPT-4 or Claude 3.5; Gemini 3.5 Flash works because the training corpus of 39 real orchestrator runs is specific and measurable. The data is the product.
3. **Silent doesn't mean unsolvable.** A run that produces zero error signals can still be autopsied if you ask the right questions in parallel. The signal is in the state, the timing, the step transitions.

---

## Technologies used

- **Backend:** Python, FastAPI, Cloud Run, Firestore, Cloud Scheduler, Vertex AI
- **Models:** Gemini 3.5 Flash (six agents, gemini-3.5-flash model)
- **Frontend:** HTML, CSS, JavaScript, server-sent events (SSE)
- **Infrastructure:** Google Cloud Platform, Docker
- **Validation:** Pattern masking (PII/secrets removal), Python deterministic metrics

---

## What's next

1. Expand the published corpus from 39 to 100+ real cases (with permission and anonymization).
2. Add support for additional languages and model providers (LLaMA, Claude) for researchers.
3. Integrate with popular orchestrator platforms (Temporal, Apache Airflow, Kubernetes operators).
4. Publish the prompts under an open license so other teams can audit and improve the investigator designs.
