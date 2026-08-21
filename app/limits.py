"""Spend limits on the endpoints that cost money.

An autopsy is six model calls and a sweep can be ten of those. Those endpoints
are open to the internet on somebody's billing account, so they get a ceiling:
a token bucket per caller and a second one for this process instance, refilled
over time. The buckets reset on a cold start; nothing here is distributed.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class Bucket:
    capacity: float
    per_second: float
    tokens: float = 0.0
    updated: float = 0.0

    def take(self, now: float, n: float = 1.0) -> bool:
        if not self.updated:                      # first use starts full
            self.tokens, self.updated = self.capacity, now
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.per_second)
        self.updated = now
        if self.tokens < n:
            return False
        self.tokens -= n
        return True

    def retry_after(self, n: float = 1.0) -> int:
        return max(1, int((n - self.tokens) / self.per_second)) if self.per_second else 3600


class Limiter:
    """One per-instance ceiling, plus a smaller one per caller."""

    def __init__(self, per_caller: tuple[float, float], per_instance: tuple[float, float]):
        self._lock = threading.Lock()
        self._callers: dict[str, Bucket] = {}
        self._instance = Bucket(*per_instance)
        self._per_caller = per_caller

    def check(self, caller: str, now: float | None = None) -> tuple[bool, int]:
        """(allowed, retry_after_seconds)."""
        now = time.time() if now is None else now
        with self._lock:
            if len(self._callers) > 4096:         # bound the dict, not the world
                self._callers.clear()
            b = self._callers.setdefault(caller, Bucket(*self._per_caller))
            if not b.take(now):
                return False, b.retry_after()
            if not self._instance.take(now):
                b.tokens += 1                     # do not charge for an instance refusal
                return False, self._instance.retry_after()
            return True, 0


# An autopsy is ~6 model calls: 5 per caller per hour.
# ponytail: the 60/hour ceiling is per instance and resets on cold starts; a
# real service-wide quota needs an atomic shared store such as Firestore.
autopsy = Limiter(per_caller=(5, 5 / 3600), per_instance=(60, 60 / 3600))
# A sweep can be ten autopsies. Scheduler needs 4/hour; leave a little headroom.
sweep = Limiter(per_caller=(8, 8 / 3600), per_instance=(12, 12 / 3600))


def demo():
    """python -m app.limits — a ceiling that does not hold is not a ceiling."""
    lim = Limiter(per_caller=(2, 1 / 60), per_instance=(3, 1 / 60))
    t = 1000.0
    assert lim.check("a", t)[0] and lim.check("a", t)[0], "first two must pass"
    ok, wait = lim.check("a", t)
    assert not ok and wait > 0, "third from the same caller must be refused with a wait"
    assert lim.check("b", t)[0], "a different caller has its own budget"
    ok, _ = lim.check("c", t)
    assert not ok, "the per-instance ceiling stops everyone once it is spent"
    # Refusals must not charge the caller: c still has its own two tokens later.
    assert lim.check("c", t + 3600)[0], "budget refills over time"
    print("OK — per-caller and per-instance ceilings both hold, and refill")


if __name__ == "__main__":
    demo()
