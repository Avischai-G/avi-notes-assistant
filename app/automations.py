"""Persistent automation definitions and runs.

Automations are data plus a stable channel binding.  They use the same
organizer and channel/context path as task chat; this module deliberately has
no agent, prompt, or execution capability of its own.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import re
import time

from app.channel_store import Message
from app.task_planning import (
    DayPlanner,
    next_jerusalem_daily,
    next_jerusalem_nine_pm,
    nightly_due,
)


_AT_TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


def next_run_from_schedule(schedule: str, now: float) -> float:
    """A trigger is free text; an explicit HH:MM makes it a real daily time.

    Anything else is a plain daily cadence from the last run.
    """
    found = _AT_TIME.search(schedule or "")
    if not found:
        return now + 86400
    return next_jerusalem_daily(now, int(found.group(1)), int(found.group(2)))


@dataclass
class Automation:
    id: str
    name: str
    prompt: str
    schedule: str
    enabled: bool
    channel_id: str
    last_run_at: float | None = None
    next_run_at: float | None = None
    state: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


KNOWLEDGE_CLEANUP = Automation(
    id="knowledge-cleanup",
    name="Knowledge cleanup",
    prompt=("Organize the scoped knowledge store: consolidate the available dream "
             "notes, record the learning event, and report a concise result. "
             "Do not perform any underlying user task."),
    schedule="daily",
    enabled=True,
    channel_id="automation-knowledge-cleanup",
)

NIGHTLY_PLAN = Automation(
    id="nightly-plan",
    name="Plan tomorrow",
    prompt="Plan tomorrow from Avi's open tasks.",
    schedule="daily at 21:00 Asia/Jerusalem",
    enabled=True,
    channel_id="automation-nightly-plan",
)

DEFAULT_AUTOMATIONS = (KNOWLEDGE_CLEANUP, NIGHTLY_PLAN)


class AutomationStore:
    def list(self) -> list[Automation]: raise NotImplementedError
    def get(self, automation_id: str) -> Automation | None: raise NotImplementedError
    def save(self, automation: Automation) -> None: raise NotImplementedError
    def delete(self, automation_id: str) -> None: raise NotImplementedError


class LocalAutomationStore(AutomationStore):
    def __init__(self, definitions: list[Automation] | None = None):
        source = definitions if definitions is not None else list(DEFAULT_AUTOMATIONS)
        self.automations = {a.id: deepcopy(a) for a in source}

    def list(self) -> list[Automation]:
        return list(self.automations.values())

    def get(self, automation_id: str) -> Automation | None:
        return self.automations.get(automation_id)

    def save(self, automation: Automation) -> None:
        self.automations[automation.id] = automation

    def delete(self, automation_id: str) -> None:
        self.automations.pop(automation_id, None)


class FirestoreAutomationStore(AutomationStore):
    def __init__(self, db): self.collection = db.collection("automations")

    @staticmethod
    def _from(data: dict) -> Automation:
        return Automation(**{k: data.get(k) for k in Automation.__dataclass_fields__})

    def list(self) -> list[Automation]:
        return [self._from({"id": doc.id, **(doc.to_dict() or {})}) for doc in self.collection.stream()]

    def get(self, automation_id: str) -> Automation | None:
        doc = self.collection.document(automation_id).get()
        return self._from({"id": doc.id, **(doc.to_dict() or {})}) if doc.exists else None

    def save(self, automation: Automation) -> None:
        self.collection.document(automation.id).set(automation.to_dict())

    def delete(self, automation_id: str) -> None:
        self.collection.document(automation_id).delete()


class KnowledgeAdapter:
    """Small Card 4 seam; production injects the knowledge consolidation store."""
    def has_dreams(self) -> bool: return False
    def consolidate(self) -> dict: raise NotImplementedError


class AutomationRunner:
    def __init__(
        self,
        store,
        channel_store,
        task_store,
        agent,
        knowledge=None,
        clock=time.time,
        planner: DayPlanner | None = None,
    ):
        self.store, self.channel_store, self.task_store = store, channel_store, task_store
        self.agent, self.knowledge, self.clock = agent, knowledge or KnowledgeAdapter(), clock
        self.planner = planner or DayPlanner(task_store)

    def _due(self, a: Automation, now: float, force: bool) -> bool:
        if force:
            return True
        if not a.enabled:
            return False
        if a.id == NIGHTLY_PLAN.id:
            return nightly_due(now, a.last_run_at)
        return a.next_run_at is None or a.next_run_at <= now

    def save_sweep(self, sweep: dict) -> None:
        automation = self.store.get(NIGHTLY_PLAN.id)
        if automation is None:
            raise RuntimeError("Nightly planning automation is not initialized")
        automation.state = {"sweep": sweep}
        self.store.save(automation)

    async def run(
        self, automation_id: str, force: bool = True, *, place: str | None = None
    ) -> dict:
        a = self.store.get(automation_id)
        if not a: raise KeyError(automation_id)
        now = self.clock()
        if not self._due(a, now, force):
            return {"status": "not-due", "automation_id": a.id, "channel_id": a.channel_id}

        if a.id == NIGHTLY_PLAN.id:
            sweep = self.planner.build(place)
            sweep["channel_id"] = a.channel_id
            a.state = {"sweep": sweep}
            a.last_run_at = now
            a.next_run_at = next_jerusalem_nine_pm(now)
            self.store.save(a)
            self.channel_store.append_message(
                a.channel_id,
                Message("assistant", sweep["text"], now),
            )
            return {
                "status": "ran",
                "automation_id": a.id,
                "channel_id": a.channel_id,
                "model_called": False,
                **sweep,
            }

        # No-work is decided before the model path, so it is deterministic and free.
        consolidation = None
        if a.id == KNOWLEDGE_CLEANUP.id:
            if not self.knowledge.has_dreams():
                a.last_run_at, a.next_run_at = now, next_run_from_schedule(a.schedule, now)
                self.store.save(a)
                message = "No dream notes to consolidate."
                self.channel_store.append_message(
                    a.channel_id, Message("assistant", message, now)
                )
                return {"status": "no-work", "automation_id": a.id, "channel_id": a.channel_id,
                        "model_called": False, "text": message}
            consolidation = self.knowledge.consolidate()

        user_message = a.prompt
        if consolidation is not None:
            user_message += "\n\nConsolidation result (context data):\n" + str(consolidation)
        chunks = []
        async for chunk in self.agent.chat(user_message, self.channel_store, self.task_store, a.channel_id):
            chunks.append(chunk)
        a.last_run_at, a.next_run_at = now, next_run_from_schedule(a.schedule, now)
        self.store.save(a)
        return {"status": "ran", "automation_id": a.id, "channel_id": a.channel_id,
                "model_called": True, "chunks": chunks, "consolidation": consolidation}

    def pick_plan(self, plan: str) -> dict:
        automation = self.store.get(NIGHTLY_PLAN.id)
        sweep = (automation.state or {}).get("sweep") if automation else None
        if automation is None or sweep is None:
            raise ValueError("No pending nightly plan")
        tasks = self.planner.pick(sweep, plan)
        now = self.clock()
        channel_id = sweep.get("channel_id") or automation.channel_id
        self.channel_store.append_message(
            channel_id, Message("user", f"Pick Plan {plan}", now)
        )
        answer = f"Plan {plan} is set for {sweep['date']}."
        self.channel_store.append_message(
            channel_id, Message("assistant", answer, now)
        )
        return {
            "status": "picked",
            "automation_id": automation.id,
            "channel_id": channel_id,
            "plan": plan,
            "scheduled_task_ids": [task.id for task in tasks],
            "text": answer,
        }

    async def tick(self) -> list[dict]:
        results = []
        for a in self.store.list():
            if a.enabled and self._due(a, self.clock(), False):
                results.append(await self.run(a.id, force=False))
        return results
