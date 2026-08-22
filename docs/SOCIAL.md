# Social Media Posts for Coroner

Every figure below is reproducible without a model call: run `python -m app.metrics`
against the shipped `data/cases/`, or `GET` the live API. Sources are listed at the
bottom of this file.

## Platform: X (Twitter)
**273 characters (limit 280), counted with the URL unshortened**

An agent run logged "CLI was stopped." It was waiting on a human who never replied.

Coroner autopsies runs that stop without erroring: six ADK agents, three in parallel.

36 of 39 died silently.

https://coroner-295057934762.us-central1.run.app

#AllThingsAgenticHackathon

---

## Platform: LinkedIn

One of the hardest failures to catch in production multi-agent systems is the silent one—no crash, no error, just stopped moving. A run politely waiting for human feedback that never arrives looks identical to a run that actually died.

Coroner is a post-mortem service that sweeps for those runs on a schedule and autopsies them unprompted. Six agents wired with Google's Agent Development Kit run over one dead trace: triage proposes candidate causes, three investigators attack them in parallel from different angles—timeline, counterfactual, competing explanation—then a certifier issues the death certificate and a reviver writes the restart plan. All six run on a single Gemini 3.5 Flash model; the diversity is in the prompts and the pipeline, not the model count.

In one published case, the run recorded its own cause of death as "The agent's interactive CLI was stopped," which the deterministic rule reads as WORKER_TERMINATED. The autopsy overturned it: all six planned steps had been handed to a human and none came back, so the certified cause was STALLED_ON_USER. The stopped CLI was the symptom. The unanswered question was the cause. Across the published corpus, the certified cause differs from the rule-based prior in 8 of 39 cases.

36 of the 39 runs (92%) stopped without ever reporting a failure. That number is not a model's opinion—it is computed from the trace before any model call, so you can reconcile it yourself from the case files in the repo.

Coroner isn't a fix. It's a working system that does what it claims, running on Cloud Run with a Cloud Scheduler sweep, and it will autopsy a trace you give it.

Live at: https://coroner-295057934762.us-central1.run.app

Built for the All Things Agentic Hackathon.

#AllThingsAgenticHackathon #MultiAgent #AI #Observability #GoogleCloud

---

## Where each claim comes from

| Claim | Source |
|---|---|
| 36 of 39 silent (92%) | `python -m app.metrics` → `silent stops: 36/39 = 92.3077%` |
| computed before any model call | `silent=t.is_silent` in `app/findings.py`; `is_silent` in `app/traces.py` |
| 8 of 39 certified ≠ rule prior | `python -m app.metrics` → `certified cause differs from rule prior: 8/39` |
| six agents, three in parallel | `IDS` and `SequentialAgent`/`ParallelAgent` in `app/autopsy.py` |
| one Gemini 3.5 Flash model | `MODEL` in `app/autopsy.py`; live `GET /api/health` → `"model": "gemini-3.5-flash"` |
| the overturned case | `GET /api/case/02266df1-6d2e-42be-8239-c243bd0896de` → prior `WORKER_TERMINATED`, certified `STALLED_ON_USER`, 6 planned steps, 0 banked |
| sweep on a schedule | Cloud Scheduler `*/15 * * * *` → `/api/sweep`; `SILENT_AFTER = 30 * 60` in `app/watch.py` |
