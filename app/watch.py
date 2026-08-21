"""The watcher — the half of the problem a diagnosis tool cannot solve.

92% of the runs in the corpus stopped without ever reporting a failure. Nobody
raised an alert, because nothing failed; the run simply stopped moving. Which
means a post-mortem service you have to *ask* only helps once you already know
somebody died, and that is exactly the thing nobody knows.

So Coroner sweeps. Any run that is still in a non-terminal state and has not
moved for longer than the threshold is presumed dead and autopsied without
being asked.

Nothing here guesses at time: `now` is always passed in, so a sweep is
reproducible and testable.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, asdict

from . import store
from .autopsy import perform_async
from .findings import extract
from .redact import redact
from .traces import load

# A run that has not moved in this long is presumed dead. Deliberately generous:
# a false autopsy costs a few cents, a missed one costs the whole run.
SILENT_AFTER = 30 * 60
TERMINAL = {"done", "failed", "complete", "completed", "cancelled"}


@dataclass
class Sweep:
    at: float
    watched: int
    silent: int
    autopsied: list[str]
    skipped_terminal: int
    already_known: int
    errors: list[str]

    def as_dict(self):
        return asdict(self)


def silent_seconds(raw: dict, now: float) -> float:
    """How long since this run last moved.

    Orchestrators record `updatedAt` in seconds or in milliseconds and rarely
    say which. Sniffing by magnitude breaks on any clock that isn't the real
    one, so pick whichever reading lands nearer `now` — that holds whatever
    epoch you hand it.
    """
    ts = raw.get("updatedAt") or 0
    if not ts:
        return float("inf")     # never stamped at all is the worst sign there is
    return max(0.0, now - min((ts, ts / 1000.0), key=lambda v: abs(now - v)))


def is_presumed_dead(raw: dict, now: float, after: float = SILENT_AFTER) -> bool:
    return (raw.get("status") or "").lower() not in TERMINAL and \
        silent_seconds(raw, now) > after


async def sweep(now: float | None = None, after: float = SILENT_AFTER,
                limit: int = 10) -> Sweep:
    """One pass. Autopsies at most `limit` runs so a cold start cannot stampede."""
    now = time.time() if now is None else now
    traces = store.all_traces()
    known = store.case_ids()

    terminal = sum(1 for r in traces if (r.get("status") or "").lower() in TERMINAL)
    dead = [r for r in traces if is_presumed_dead(r, now, after)]
    fresh = [r for r in dead if (r.get("runId") or "") not in known]

    done: list[str] = []
    errors: list[str] = []
    for raw in fresh[:limit]:
        try:
            t = load(raw)
            t = redact(t)
            report = await perform_async(t, extract(t))
            store.save(report.as_dict())
            done.append(report.run_id)
        except Exception as e:                       # one bad trace must not stop the sweep
            errors.append(f"{raw.get('runId', '?')[:8]}: {type(e).__name__}: {str(e)[:120]}")

    result = Sweep(at=now, watched=len(traces), silent=len(dead), autopsied=done,
                   skipped_terminal=terminal, already_known=len(dead) - len(fresh),
                   errors=errors)
    store.put_meta("sweep", result.as_dict())
    return result


def demo():
    """python -m app.watch — the branch that decides who gets cut open."""
    now = 1_000_000.0
    running_stale = {"status": "held", "updatedAt": (now - 3600) * 1000}
    running_fresh = {"status": "held", "updatedAt": (now - 60) * 1000}
    finished_stale = {"status": "done", "updatedAt": (now - 99999) * 1000}
    never_stamped = {"status": "running"}

    assert is_presumed_dead(running_stale, now)
    assert not is_presumed_dead(running_fresh, now), "a run that just moved is not dead"
    assert not is_presumed_dead(finished_stale, now), "finished runs are not corpses"
    assert is_presumed_dead(never_stamped, now), "no timestamp at all is the worst sign"
    assert silent_seconds({"updatedAt": (now - 120) * 1000}, now) == 120
    # Seconds-precision timestamps must not be read as milliseconds.
    assert silent_seconds({"updatedAt": now - 120}, now) == 120
    print("OK — stale non-terminal runs are swept, fresh and finished ones are left alone")


if __name__ == "__main__":
    demo()
