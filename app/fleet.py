"""Fleet view: what one graveyard says that one grave cannot.

A single autopsy tells you why one run died. It is mildly interesting. The
useful question is the one you can only ask across the whole graveyard: of all
the changes we could make to the orchestrator, which one change would have
saved the most runs?

Discipline that matters here: **the numbers are counted, the judgment is
modelled.** Everything in `Aggregate` is computed in Python from the traces.
The agent is handed those numbers and asked only to group the preventions.
Python validates the returned run IDs, counts them and ranks the groups.
"""
from __future__ import annotations

import asyncio
import collections
from dataclasses import dataclass, asdict

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from .autopsy import MODEL, APP
from .findings import CAUSES


@dataclass
class Aggregate:
    """Counted, never modelled."""
    runs: int
    by_cause: dict[str, int]
    silent_stops: int
    silent_rate: float
    mean_progress: float
    steps_planned: int
    steps_banked: int
    steps_abandoned: int
    revivable: int

    def as_dict(self):
        return asdict(self)


def aggregate(cases: list[dict]) -> Aggregate:
    by_cause = collections.Counter()
    silent = planned = banked = revivable = 0
    progress: list[float] = []

    for c in cases:
        cause = (c.get("certificate") or {}).get("cause") or c.get("prior_cause") or "UNDETERMINED"
        by_cause[cause] += 1
        ev = c.get("evidence") or {}
        if ev.get("silent"):
            silent += 1
        n = int(ev.get("steps_planned") or 0)
        planned += n
        banked += round(float(ev.get("progress") or 0.0) * n)
        if cause != "USER_ABORT":
            progress.append(float(ev.get("progress") or 0.0))
        if (c.get("resume_plan") or {}).get("revivable"):
            revivable += 1

    n = len(cases) or 1
    return Aggregate(
        runs=len(cases),
        by_cause=dict(by_cause.most_common()),
        silent_stops=silent,
        silent_rate=silent / n,
        mean_progress=(sum(progress) / len(progress)) if progress else 0.0,
        steps_planned=planned,
        steps_banked=banked,
        steps_abandoned=planned - banked,
        revivable=revivable,
    )


class Prescription(BaseModel):
    change: str = Field(description="one concrete change to the orchestrator, specific enough to assign")
    rationale: str = Field(description="one sentence: why this class of death happens")
    run_ids: list[str] = Field(description="the run ids this change would have saved")
    effort: str = Field(description="small | medium | large")


class Prescriptions(BaseModel):
    prescriptions: list[Prescription]


_PRESCRIBE = """You are reviewing every post-mortem from one fleet of AI agents.

THE COUNTED FACTS (these are computed from the traces; treat them as ground
truth and never contradict or recompute them)
{facts}

THE INDIVIDUAL CERTIFICATES
{certificates}

YOUR JOB
Every certificate proposed a prevention for its own run. Most of those are the
same handful of fixes said in different words. Collapse them.

Return the orchestrator-change groups. Python validates the run IDs, counts
them, ranks the groups and writes the numerical headline.

- Merge preventions that are the same change described differently. Be
  aggressive about this: two fixes that touch the same component for the same
  underlying reason are one ticket, not two. Aim for at most six entries.
- Do not emit a prescription that saves a single run unless no other
  prescription could plausibly cover it.
- A change may only claim a run if that run's certified cause would actually
  have been averted by it. Do not pad the counts; a smaller honest number is
  worth more than a large one.
- 'change' must be specific enough to hand to an engineer as a ticket. Not
  "improve error handling" — name the component and what it should do instead.
- Ignore USER_ABORT runs. A human stopping a run on purpose is not a defect
  and there is nothing to prevent.
"""


def _fmt(cases: list[dict]) -> str:
    out = []
    for c in cases:
        cert = c.get("certificate") or {}
        if not cert:
            continue
        out.append(
            f"- run {c.get('run_id','?')[:8]} | cause {cert.get('cause','?')} | "
            f"banked {float((c.get('evidence') or {}).get('progress') or 0):.0%}\n"
            f"    what happened: {cert.get('plain_english','')[:300]}\n"
            f"    proposed fix:  {cert.get('prevention','')[:300]}"
        )
    return "\n".join(out)


def _facts(a: Aggregate) -> str:
    causes = "\n".join(
        f"    {k:<22} {v:>3}  {CAUSES.get(k, (k,))[0]}" for k, v in a.by_cause.items())
    return f"""  runs examined: {a.runs}
  stopped without ever reporting a failure: {a.silent_stops} ({a.silent_rate:.0%})
  mean share of planned work banked before death: {a.mean_progress:.1%}
  steps planned across the fleet: {a.steps_planned}
  steps banked: {a.steps_banked}
  steps abandoned: {a.steps_abandoned}
  runs judged revivable: {a.revivable}
  causes of death:
{causes}"""


def finalize(grouped: dict, cases: list[dict], a: Aggregate | None = None) -> dict:
    """Validate model groupings and add every number deterministically."""
    a = a or aggregate(cases)
    full_ids = [str(c.get("run_id") or "") for c in cases if c.get("run_id")]
    exact = {run_id: run_id for run_id in full_ids}
    by_prefix: dict[str, list[str]] = collections.defaultdict(list)
    for run_id in full_ids:
        by_prefix[run_id[:8]].append(run_id)
    aliases = {prefix: matches[0] for prefix, matches in by_prefix.items()
               if len(matches) == 1}

    seen: set[str] = set()
    unknown = duplicates = 0
    prescriptions = []
    raw_groups = grouped.get("prescriptions") if isinstance(grouped, dict) else []
    for raw in raw_groups if isinstance(raw_groups, list) else []:
        if not isinstance(raw, dict):
            continue
        validated = []
        raw_ids = raw.get("run_ids") or []
        for candidate in raw_ids if isinstance(raw_ids, list) else []:
            if not isinstance(candidate, str):
                unknown += 1
                continue
            run_id = exact.get(candidate) or aliases.get(candidate)
            if not run_id:
                unknown += 1
                continue
            if run_id in seen:
                duplicates += 1
                continue
            seen.add(run_id)
            validated.append(run_id[:8] if len(by_prefix[run_id[:8]]) == 1 else run_id)
        prescriptions.append({
            "change": raw.get("change") or "",
            "rationale": raw.get("rationale") or "",
            "run_ids": validated,
            "effort": raw.get("effort") or "",
            "deaths_prevented": len(validated),
        })

    prescriptions.sort(key=lambda p: p["deaths_prevented"], reverse=True)
    return {
        "aggregate": a.as_dict(),
        "prescriptions": prescriptions,
        "headline": (
            f"{a.silent_rate:.0%} of {a.runs} runs stopped without reporting a failure; "
            f"{a.steps_abandoned} planned steps were abandoned."
        ),
        "unknown_run_ids": unknown,
        "duplicate_run_ids": duplicates,
    }


prescriber = LlmAgent(
    name="prescriber",
    model=MODEL,
    description="Ranks the orchestrator changes that would have saved the most runs.",
    instruction=_PRESCRIBE,
    output_schema=Prescriptions,
    output_key="prescriptions",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    generate_content_config=types.GenerateContentConfig(temperature=0.2),
)


async def prescribe_async(cases: list[dict]) -> dict:
    a = aggregate(cases)
    sessions = InMemorySessionService()
    runner = Runner(app_name=APP, agent=prescriber, session_service=sessions)
    s = await sessions.create_session(
        app_name=APP, user_id="coroner",
        state={"facts": _facts(a), "certificates": _fmt(cases)})
    async for _ in runner.run_async(
        user_id="coroner", session_id=s.id,
        new_message=types.Content(role="user", parts=[types.Part(text="Prescribe.")]),
    ):
        pass
    st = (await sessions.get_session(app_name=APP, user_id="coroner", session_id=s.id)).state

    from .autopsy import _parse
    return finalize(_parse(st.get("prescriptions")), cases, a)


def prescribe(cases: list[dict]) -> dict:
    return asyncio.run(prescribe_async(cases))
