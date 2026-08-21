"""Canonical trace format + adapters.

A trace is whatever an orchestrator left behind when a run stopped. Every
orchestrator writes something different, so everything upstream of this module
is vendor-specific and everything downstream is not.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Step:
    id: str
    title: str
    agent: str = ""
    status: str = ""          # done | doing | todo | blocked | user | unknown
    depends_on: list[str] = field(default_factory=list)
    difficulty: str = ""
    instruction: str = ""     # what the worker was told to do
    acceptance: str = ""      # how the orchestrator would have judged it
    result: str = ""          # what the worker reported back, if anything
    attempts: int = 0         # retries are evidence: a step tried 3 times died differently


@dataclass
class Trace:
    run_id: str
    title: str
    final_state: str          # held | running | done | failed
    stop_reason: str          # verbatim, whatever the orchestrator said
    request: str              # what the human originally asked for
    steps: list[Step] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    worker_failures: int = 0
    source: str = "unknown"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    # --- derived signals the analyst agents reason over -------------------
    @property
    def counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for s in self.steps:
            c[s.status or "unknown"] = c.get(s.status or "unknown", 0) + 1
        return c

    @property
    def progress(self) -> float:
        """Fraction of planned steps actually banked. The number that matters."""
        if not self.steps:
            return 0.0
        return len([s for s in self.steps if s.status == "done"]) / len(self.steps)

    @property
    def retries(self) -> int:
        return sum(max(0, s.attempts - 1) for s in self.steps)

    @property
    def is_silent(self) -> bool:
        """Stopped without ever reporting a failure. The dangerous kind."""
        return self.final_state in ("held", "running") and self.worker_failures == 0


def from_agentonomy(raw: dict[str, Any], run_id: str = "") -> Trace:
    """Adapter for Agentonomy held-run JSON."""
    steps = [
        Step(
            id=str(s.get("taskId") or s.get("step") or i),
            title=(s.get("title") or "").strip(),
            agent=s.get("agent") or "",
            status=s.get("status") or "unknown",
            depends_on=[str(d) for d in (s.get("dependsOn") or [])],
            difficulty=s.get("difficulty") or "",
            instruction=(s.get("instruction") or "").strip(),
            acceptance=(s.get("acceptance") or "").strip(),
            result=(s.get("result") or "").strip() if isinstance(s.get("result"), str)
                   else json.dumps(s.get("result")) if s.get("result") else "",
            attempts=int(s.get("attempts") or 0),
        )
        for i, s in enumerate(raw.get("steps") or [])
    ]
    return Trace(
        run_id=raw.get("runId") or run_id or raw.get("chatId") or "unknown",
        title=(raw.get("title") or "").strip() or "(untitled run)",
        final_state=raw.get("status") or "unknown",
        stop_reason=(raw.get("reason") or "").strip(),
        request=(raw.get("originalRequest") or "").strip(),
        steps=steps,
        completed=[str(c) for c in (raw.get("completedSteps") or [])],
        worker_failures=int(raw.get("cliFailures") or 0),
        source="agentonomy",
    )


ADAPTERS = {"agentonomy": from_agentonomy}


def detect(raw: dict[str, Any]) -> str:
    if "runId" in raw and "steps" in raw:
        return "agentonomy"
    raise ValueError("unrecognised trace format")


def load(raw: dict[str, Any], run_id: str = "") -> Trace:
    return ADAPTERS[detect(raw)](raw, run_id)
