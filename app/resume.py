"""Handing the restart back.

A post-mortem that stops at a diagnosis is a report generator. The point of
working out that a run is revivable, which steps are already banked and what
assumption to proceed under is to give that to something that can act on it.

Coroner does not know your orchestrator, so the contract is the smallest one
that can work: a POST of the resume plan to a URL you configure. If the
delivery fails, that is reported — never swallowed, because a restart you
believe happened and did not is worse than no restart at all.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict

WEBHOOK = "CORONER_RESUME_WEBHOOK"
TIMEOUT = 20


@dataclass
class Delivery:
    delivered: bool
    status: int | None
    detail: str
    endpoint: str = ""

    def as_dict(self):
        return asdict(self)


def payload(case: dict) -> dict:
    """What an orchestrator needs to pick the run back up. Nothing else."""
    plan = case.get("resume_plan") or {}
    cert = case.get("certificate") or {}
    return {
        "run_id": case.get("run_id"),
        "title": case.get("title"),
        "cause_of_death": cert.get("cause"),
        "confidence": cert.get("confidence"),
        "resume_at": plan.get("resume_at"),
        "skip": plan.get("skip") or [],
        "proceed_under": plan.get("unblock"),
        "restart_prompt": plan.get("restart_prompt"),
        "salvage": plan.get("salvage"),
    }


def hand_back(case: dict, endpoint: str | None = None, _post=None) -> Delivery:
    """Deliver the resume plan. `_post` is the seam the self-check drives."""
    url = endpoint or os.environ.get(WEBHOOK, "")
    if not url:
        return Delivery(False, None, f"no orchestrator configured (set {WEBHOOK})")

    plan = case.get("resume_plan") or {}
    if not plan.get("revivable"):
        return Delivery(False, None, "not revivable — nothing to hand back", url)
    if not plan.get("restart_prompt"):
        return Delivery(False, None, "revivable but no restart prompt was written", url)

    body = json.dumps(payload(case)).encode()
    try:
        if _post:
            status, text = _post(url, body)
        else:
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={"content-type": "application/json", "user-agent": "coroner/1"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                status, text = r.status, r.read(400).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return Delivery(False, e.code, f"orchestrator refused it: {e.reason}", url)
    except Exception as e:
        return Delivery(False, None, f"{type(e).__name__}: {str(e)[:160]}", url)

    ok = 200 <= status < 300
    return Delivery(ok, status, text.strip()[:200] or ("accepted" if ok else "rejected"), url)


def demo():
    """python -m app.resume — a delivery that silently fails is the failure mode."""
    live = {"run_id": "r1", "title": "t", "certificate": {"cause": "STALLED_ON_USER"},
            "resume_plan": {"revivable": True, "restart_prompt": "carry on",
                            "resume_at": "s3", "skip": ["s1", "s2"], "unblock": "assume weekly"}}
    dead = {"run_id": "r2", "resume_plan": {"revivable": False}}
    mute = {"run_id": "r3", "resume_plan": {"revivable": True, "restart_prompt": ""}}

    seen = {}
    def ok(url, body):
        seen["body"] = json.loads(body)
        return 202, "queued"

    d = hand_back(live, "http://example.invalid/resume", _post=ok)
    assert d.delivered and d.status == 202, d
    assert seen["body"]["resume_at"] == "s3" and seen["body"]["skip"] == ["s1", "s2"]
    assert seen["body"]["restart_prompt"] == "carry on"

    assert not hand_back(dead, "http://x", _post=ok).delivered, "must not resume a finished run"
    assert not hand_back(mute, "http://x", _post=ok).delivered, "must not resume with no instruction"
    assert not hand_back(live, "", _post=ok).delivered, "no endpoint configured is not a success"

    def boom(url, body):
        raise TimeoutError("no route to host")
    d = hand_back(live, "http://x", _post=boom)
    assert not d.delivered and "TimeoutError" in d.detail, d

    def refused(url, body):
        return 500, "orchestrator on fire"
    assert not hand_back(live, "http://x", _post=refused).delivered

    print("OK — delivers when it should, and reports every way it can fail")


if __name__ == "__main__":
    demo()
