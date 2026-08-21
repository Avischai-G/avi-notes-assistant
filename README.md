# Coroner

**Agent runs don't crash. They ghost you.**

Coroner performs an autopsy on a multi-agent run that stopped without finishing,
and tells you what actually killed it.

## Why

Read 38 real dead multi-agent runs off one developer's disk:

| | |
|---|---|
| Runs that stopped **without ever reporting a failure** | **95%** (36/38) |
| Mean share of planned work actually banked before death | **18.5%** |
| Largest single cause | recovered from an older session, then never resumed (12 runs) |

Nothing was on fire. No exception was thrown. The board still looked busy.
Every one of those runs was quietly waiting, blocked, or orphaned — and the
only signal was that progress stopped, which no dashboard reports.

That is the gap. Monitoring tells you an agent is *running*. Nothing tells you
it has stopped *mattering*.

## How

Three agents, on Gemini via Vertex AI:

1. **Triage** reads the trace and proposes 2–3 candidate causes — explicitly
   allowed to overrule the rule-based guess, since a recorded stop reason
   usually names the symptom, not the cause.
2. **Investigators** run in parallel, one per hypothesis, each instructed to
   *disprove* the hypothesis it was handed. A story that survives a hostile
   reader is worth something; one that survives a friendly reader is not.
3. **The coroner** weighs the surviving hypotheses, picks the earliest cause in
   the causal chain, and issues a death certificate: cause, the step it died on,
   what was wasted, and one concrete change that would have prevented it.

If nothing survives, the verdict is UNDETERMINED. It is not allowed to invent a
cause to avoid saying so.

## Cause-of-death taxonomy

Not invented — read off the corpus. See `app/findings.py`.

`STALLED_ON_USER` · `ZOMBIE_RECOVERY` · `VERIFICATION_DEADLOCK` · `INFRA_RESTART`
· `WORKER_TERMINATED` · `TIMEOUT` · `TURN_CEILING` · `USER_ABORT` · `UNDETERMINED`

## Check

```bash
python3 test_corpus.py            # runs the taxonomy over the real corpus
```

Asserts every trace parses, every cause is in the vocabulary, and that the
taxonomy explains at least 85% of the corpus. Currently 37/38.

## Status

- [x] canonical trace format + Agentonomy adapter
- [x] taxonomy + deterministic evidence extraction, validated on 38 real traces
- [x] three-stage adversarial agent pipeline
- [ ] `gcloud auth login` — then the pipeline can actually run
- [ ] HTTP service + Cloud Run deploy
- [ ] the case-file UI
- [ ] adapters beyond Agentonomy

## Note on the corpus

The 38 traces are real and contain real project content. They are the reason the
taxonomy is trustworthy, but they **must be anonymised or replaced with
shape-preserving synthetic traces before anything ships publicly.**
