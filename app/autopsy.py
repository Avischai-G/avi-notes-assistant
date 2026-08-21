"""The autopsy: five agents over one dead run, wired with Google ADK.

    triage        proposes candidate causes, including ones the rules missed
    investigation three investigators in parallel, each with a different lens,
                  each told to DESTROY the hypotheses rather than confirm them
    certify       weighs the verdicts and issues the death certificate
    revive        writes the resume plan — the part that makes this more than
                  a report generator

The middle stage is deliberately adversarial and deliberately diverse. The
failure mode of an LLM reading a broken run is to agree with the first
plausible story; three identical skeptics agree with each other. Three
different lenses do not.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, asdict

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from .findings import CAUSES, Evidence
from .traces import Trace

MODEL = os.environ.get("CORONER_MODEL", "gemini-3.5-flash")
APP = "coroner"

_VOCAB = "\n".join(f"  {k}: {v[1]}" for k, v in CAUSES.items())


# --- what each stage must return -----------------------------------------
class Hypothesis(BaseModel):
    cause: str = Field(description="one key from the taxonomy")
    reasoning: str
    confidence: float


class Triage(BaseModel):
    hypotheses: list[Hypothesis]


class Verdict(BaseModel):
    cause: str = Field(description="the hypothesis this verdict is about")
    survives: bool
    argument: str
    evidence: list[str]


class Investigation(BaseModel):
    verdicts: list[Verdict]


class Certificate(BaseModel):
    cause: str
    confidence: float
    plain_english: str = Field(
        description="two or three sentences for the engineer who owns this system")
    killing_step: str
    contributing: list[str]
    wasted_effort: str
    prevention: str = Field(
        description="one concrete change to the orchestrator, not advice")


class ResumePlan(BaseModel):
    revivable: bool = Field(description="false if the run is genuinely finished or was aborted on purpose")
    resume_at: str = Field(description="step id to restart from, or '' if not revivable")
    skip: list[str] = Field(description="step ids already banked; do not redo these")
    unblock: str = Field(description="the single thing that must be true before restarting")
    restart_prompt: str = Field(
        description="the exact instruction to hand the orchestrator to resume this run")
    salvage: str = Field(description="what of the dead run's work is still worth keeping")


# --- the brief every agent reads -----------------------------------------
def _detail(s) -> str:
    """The forensic detail for one step. Only worth spending tokens on the
    steps that were actually in flight or that fought before they died."""
    out = [f"  step {s.id[:8]} [{s.status}] attempts={s.attempts or 1}",
           f"    title: {s.title[:200]}"]
    if s.instruction:
        out.append(f"    was told to: {s.instruction[:500]}")
    if s.acceptance:
        out.append(f"    would have passed if: {s.acceptance[:300]}")
    if s.result:
        out.append(f"    reported back: {s.result[:900]}")
    return "\n".join(out)


def brief(t: Trace, ev: Evidence) -> str:
    board = "\n".join(
        f"  [{s.status:<8}] {s.id[:8]} {s.title[:110]}" for s in t.steps[:40]
    ) or "  (no steps were ever planned)"

    # The steps worth reading in full: whatever was in flight, plus anything
    # that had to retry. A step that tried three times died differently from
    # one that never started.
    interesting = [s for s in t.steps
                   if s.status in ("doing", "blocked", "user") or s.attempts > 1]
    detail = "\n\n".join(_detail(s) for s in interesting[:6])

    return f"""RUN {t.run_id}
title: {t.title}
final state: {t.final_state}
stop reason as recorded: {t.stop_reason or "(none recorded)"}
what the human originally asked for: {t.request[:600] or "(not recorded)"}

the board as it was left:
{board}

the steps that were in flight or fought before they died:
{detail or "  (none — nothing was in flight when the run stopped)"}

observations already extracted from the trace:
{chr(10).join("  - " + s for s in ev.signals)}
step the run appears to have died on: {ev.killing_step or "(not identifiable)"}
rule-based first guess: {ev.prior_cause}
"""


_CASE = """You are examining a multi-agent run that stopped without finishing.

THE CASE FILE
{brief}

KNOWN CAUSES OF DEATH
""" + _VOCAB + "\n"


def _agent(name: str, schema, key: str, instruction: str) -> LlmAgent:
    return LlmAgent(
        name=name,
        model=MODEL,
        instruction=_CASE + instruction,
        output_schema=schema,
        output_key=key,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=types.GenerateContentConfig(temperature=0.2),
    )


triage = _agent("triage", Triage, "triage", """
YOUR JOB
Propose 2-3 candidate causes of death, most likely first.

The rule-based guess matches on the stop-reason string, so it is fooled
whenever the recorded reason describes the symptom rather than the cause. A run
that says it is "waiting for the user" may really have died because something
upstream forced it to ask. Treat the guess as one hypothesis among others.

If the recorded stop reason looks like the proximate symptom of something
earlier in the run, say so and propose the earlier cause as well.
""")


# Three lenses, not three copies. Redundant skeptics agree with each other;
# skeptics looking for different things do not.
_LENSES = {
    "sequence": """
YOUR LENS: the timeline.
For each hypothesis, ask whether the order of events actually supports it. Find
the earliest point where this run diverged from a healthy one. If a hypothesis
names something that happened AFTER that divergence, it is a symptom, not the
cause, and it does not survive.""",
    "counterfactual": """
YOUR LENS: the counterfactual.
For each hypothesis, ask: if this cause were removed and nothing else changed,
would the run have finished? If the answer is no — if it would have stalled
somewhere else anyway — then this is not the cause of death and it does not
survive.""",
    "alternative": """
YOUR LENS: the competing explanation.
For each hypothesis, actively construct a different explanation that fits every
observation at least as well. If you can build one, the hypothesis does not
survive. Consider mundane explanations before exotic ones, and consider that
the run may have behaved correctly and the surrounding system failed it.""",
}

investigators = [
    _agent(f"investigator_{lens}", Investigation, f"verdicts_{lens}", f"""
CANDIDATE CAUSES PROPOSED AT TRIAGE
{{triage}}
{prompt}

Return one verdict per candidate cause above. Your job is to DESTROY them, not
to confirm them. Only mark a hypothesis as surviving if you genuinely could not
break it through your lens. Cite specific steps or observations; never restate
a hypothesis back as evidence for itself. If the trace is too thin to decide,
that is a failure to survive — say so.""")
    for lens, prompt in _LENSES.items()
]

certify = _agent("certify", Certificate, "certificate", """
CANDIDATE CAUSES PROPOSED AT TRIAGE
{triage}

Each candidate was handed to three investigators with different lenses, all
instructed to destroy it.

  timeline lens:        {verdicts_sequence}
  counterfactual lens:  {verdicts_counterfactual}
  competing-explanation lens: {verdicts_alternative}

YOUR JOB
Issue the death certificate.

- A cause survives only if it survived a MAJORITY of the three lenses.
- If several survived, choose the earliest one in the causal chain. The others
  are its symptoms; list them as contributing factors.
- If none survived, the cause is UNDETERMINED and confidence is low. Do not
  invent a cause to avoid saying so.
- 'plain_english' is addressed to the engineer who owns this system. No
  hedging, and do not recite the taxonomy definition back at them.
- 'wasted_effort' states how much of the planned work was thrown away.
- 'prevention' is one concrete change to the orchestrator. Not advice, not a
  principle — a change someone could make on Monday.
""")

revive = _agent("revive", ResumePlan, "resume_plan", """
CAUSE OF DEATH AS CERTIFIED
{certificate}

YOUR JOB
Write the resume plan. This run's remaining work is not automatically lost —
decide what can still be salvaged and how to restart it.

- 'revivable' is false only if the run genuinely completed, was aborted on
  purpose by a human, or its request no longer makes sense. Being stuck is not
  a reason to declare it unrevivable.
- 'skip' lists the step ids already banked so the restart does not redo them.
- 'unblock' is the single condition that must hold before restarting. If the
  run died waiting on a human, do NOT write "the user must answer" — that is
  what already failed. Write the assumption the orchestrator should proceed
  under instead, chosen so that being wrong is cheap and visible.
- 'restart_prompt' is handed verbatim to the orchestrator. Never assert
  anything that has not happened — in particular never claim the human
  answered. State the assumption openly, instruct the orchestrator to proceed
  on it and to flag it in its output, and carry forward what is already done.
""")

coroner = SequentialAgent(
    name="coroner",
    description="Determines why a multi-agent run died, and how to restart it.",
    sub_agents=[
        triage,
        ParallelAgent(name="investigation", sub_agents=investigators),
        certify,
        revive,
    ],
)


# --- running it -----------------------------------------------------------
@dataclass
class Report:
    run_id: str
    title: str
    prior_cause: str
    evidence: dict
    hypotheses: list[dict]
    verdicts: dict
    certificate: dict
    resume_plan: dict

    def as_dict(self):
        return asdict(self)


def _parse(v):
    """ADK stores structured output as a dict, but as a JSON string on some paths."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return {}
    return v or {}


async def _run(t: Trace, ev: Evidence, on_event=None) -> dict:
    """Drive the ADK pipeline and hand back the final session state."""
    sessions = InMemorySessionService()
    runner = Runner(app_name=APP, agent=coroner, session_service=sessions)
    s = await sessions.create_session(
        app_name=APP, user_id="coroner", state={"brief": brief(t, ev)})

    async for e in runner.run_async(
        user_id="coroner", session_id=s.id,
        new_message=types.Content(role="user", parts=[types.Part(text="Begin the autopsy.")]),
    ):
        if on_event:
            delta = dict((e.actions.state_delta or {}) if e.actions else {})
            await on_event({"agent": e.author,
                            "final": bool(e.is_final_response()),
                            "produced": {k: _parse(v) for k, v in delta.items()}})

    return (await sessions.get_session(
        app_name=APP, user_id="coroner", session_id=s.id)).state


def _report(t: Trace, ev: Evidence, st: dict) -> Report:
    return Report(
        run_id=t.run_id,
        title=t.title,
        prior_cause=ev.prior_cause,
        evidence={"signals": ev.signals, "progress": ev.progress,
                  "killing_step": ev.killing_step, "silent": ev.silent,
                  "steps_planned": len(t.steps), "retries": t.retries,
                  "stop_reason": t.stop_reason, "final_state": t.final_state},
        hypotheses=_parse(st.get("triage")).get("hypotheses", []),
        verdicts={lens: _parse(st.get(f"verdicts_{lens}")).get("verdicts", [])
                  for lens in _LENSES},
        certificate=_parse(st.get("certificate")),
        resume_plan=_parse(st.get("resume_plan")),
    )


async def perform_async(t: Trace, ev: Evidence, on_event=None) -> Report:
    return _report(t, ev, await _run(t, ev, on_event))


def perform(t: Trace, ev: Evidence) -> Report:
    return asyncio.run(perform_async(t, ev))


# The stages a caller can expect, in order, so a UI can draw the pipeline
# before the first event arrives.
STAGES = [
    ("triage", "Triage", "proposes candidate causes"),
    ("investigator_sequence", "Timeline lens", "tries to break them on the order of events"),
    ("investigator_counterfactual", "Counterfactual lens", "tries to break them on cause and effect"),
    ("investigator_alternative", "Competing-explanation lens", "tries to break them with a better story"),
    ("certify", "Certification", "issues the death certificate"),
    ("revive", "Revival", "writes the resume plan"),
]
