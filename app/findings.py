"""Cause-of-death taxonomy and deterministic evidence extraction.

The taxonomy is not invented. It is what 38 real dead multi-agent runs
actually died of, read off disk. Extraction here is cheap and deterministic;
judgment is left to the agents in autopsy.py, which reason over these signals
rather than re-deriving them from raw JSON.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

from .traces import Trace

# cause -> (human label, what it means, what would have prevented it)
CAUSES: dict[str, tuple[str, str, str]] = {
    "STALLED_ON_USER": (
        "Stalled waiting for a human",
        "The run parked on a question and nobody ever answered. It is not failed; "
        "it is still politely waiting, and it will wait forever.",
        "Let the agent decide and proceed under a stated assumption, reserving "
        "questions for choices that are genuinely the human's to make.",
    ),
    "ZOMBIE_RECOVERY": (
        "Recovered but never resumed",
        "The run was carried over from an older session and re-planned, but no "
        "step ever moved after the recovery. It looks alive on the board.",
        "Treat recovery as a state that must exit within one turn: either work "
        "resumes or the run is closed out.",
    ),
    "VERIFICATION_DEADLOCK": (
        "Blocked after verification",
        "Verification refused the work and left every step blocked, with no path "
        "that would ever unblock them.",
        "A failing verification must emit a next action, not just a verdict.",
    ),
    "INFRA_RESTART": (
        "Killed by a restart",
        "The orchestrator process restarted mid-run and the work did not survive it.",
        "Checkpoint step state so a restart resumes instead of orphaning.",
    ),
    "WORKER_TERMINATED": (
        "Worker process stopped",
        "The agent's own CLI stopped before it reported anything back.",
        "Supervise workers and re-launch on unexpected exit.",
    ),
    "TIMEOUT": (
        "Ran out of wall clock",
        "The run exceeded its time ceiling while still working.",
        "Budget per-step, not per-run, so one slow step cannot consume the whole allowance.",
    ),
    "TURN_CEILING": (
        "Looped until it ran out of turns",
        "The orchestrator kept taking turns without converging and hit its ceiling.",
        "Detect repeated no-progress turns and break out early.",
    ),
    "USER_ABORT": (
        "Stopped on purpose",
        "A human stopped this run. Not a defect.",
        "Nothing to prevent.",
    ),
    "UNDETERMINED": (
        "Undetermined",
        "The trace does not say enough to attribute a cause.",
        "Record a stop reason on every terminal transition.",
    ),
}

# Ordered: first match wins. Patterns are read off the real corpus.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("USER_ABORT",           re.compile(r"\buser stopped\b", re.I)),
    ("STALLED_ON_USER",      re.compile(r"\bwaiting for the user\b", re.I)),
    ("ZOMBIE_RECOVERY",      re.compile(r"\brecovered unfinished work\b", re.I)),
    ("VERIFICATION_DEADLOCK",re.compile(r"\bremain blocked after verification\b", re.I)),
    ("TURN_CEILING",         re.compile(r"\bturn ceiling\b", re.I)),
    ("TIMEOUT",              re.compile(r"did not finish within \d+ seconds", re.I)),
    ("INFRA_RESTART",        re.compile(r"\brestarted before this run finished\b|\bduring (?:an?|the) [\w-]+ restart\b", re.I)),
    ("WORKER_TERMINATED",    re.compile(r"\bCLI was stopped\b|\bCLI stopped\b", re.I)),
]


@dataclass
class Evidence:
    """What the trace shows, before anyone interprets it."""
    prior_cause: str            # rule-based first guess, for the agents to challenge
    signals: list[str]          # plain-language observations
    killing_step: str | None    # the step the run died on, if identifiable
    progress: float
    silent: bool


def _killing_step(t: Trace) -> str | None:
    """The step that was in flight, or the first thing standing in the way."""
    for want in ("user", "doing", "blocked"):
        for s in t.steps:
            if s.status == want:
                return f"{s.id} — {s.title[:120]}"
    return None


def classify(t: Trace) -> str:
    for cause, pat in _RULES:
        if pat.search(t.stop_reason):
            return cause
    return "UNDETERMINED"


def extract(t: Trace) -> Evidence:
    sig: list[str] = []
    c = t.counts
    total = len(t.steps)

    if total:
        sig.append(
            f"{total} steps planned; banked {int(t.progress * total)} "
            f"({t.progress:.0%}). Step states: "
            + ", ".join(f"{k}={v}" for k, v in sorted(c.items()))
        )
    else:
        sig.append("No steps were ever planned — the run died before decomposition.")

    if any(s.status == "done" for s in t.steps) and not t.completed:
        sig.append(
            "completedSteps is empty even though steps are marked done — the "
            "run's own ledger disagrees with its board."
        )
    if t.is_silent:
        sig.append(
            "Stopped with zero reported worker failures: this run never announced "
            "a problem, it simply stopped making progress."
        )
    if c.get("blocked"):
        sig.append(f"{c['blocked']} step(s) sitting in 'blocked' with no unblocking action recorded.")
    if c.get("user"):
        sig.append(f"{c['user']} step(s) handed back to the human and never returned.")
    if t.retries:
        worst = max(t.steps, key=lambda x: x.attempts)
        sig.append(
            f"{t.retries} retry/retries across the plan; worst was step "
            f"{worst.id[:8]} at {worst.attempts} attempts — it fought before it died.")
    if t.worker_failures:
        sig.append(f"{t.worker_failures} worker CLI failure(s) recorded.")
    if not t.stop_reason:
        sig.append("No stop reason was recorded at all.")

    return Evidence(
        prior_cause=classify(t),
        signals=sig,
        killing_step=_killing_step(t),
        progress=t.progress,
        silent=t.is_silent,
    )
