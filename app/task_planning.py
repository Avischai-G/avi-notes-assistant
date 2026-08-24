"""Small, deterministic policy for defaults and tomorrow's two plans."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
import re
from typing import Callable, Iterable
import uuid
from zoneinfo import ZoneInfo

from app.task_store import Task, TaskStore


JERUSALEM = ZoneInfo("Asia/Jerusalem")
DONE = "Done"
ANYWHERE = "Anywhere"
DEFAULT_MINUTES = 30
DAY_MINUTES = 8 * 60
DAY_START = time(9, 0)
_UNSET = object()


def local_now(clock: Callable[[], datetime] | None = None) -> datetime:
    value = clock() if clock else datetime.now(JERUSALEM)
    if value.tzinfo is None:
        value = value.replace(tzinfo=JERUSALEM)
    return value.astimezone(JERUSALEM)


def tomorrow_iso(clock: Callable[[], datetime] | None = None) -> str:
    return (local_now(clock).date() + timedelta(days=1)).isoformat()


def infer_when(
    message: str,
    supplied: str | None,
    clock: Callable[[], datetime] | None = None,
) -> str | None:
    """Resolve the assistant's date defaults in Jerusalem, never UTC."""
    today = local_now(clock).date()
    lowered = message.casefold()
    if supplied is not None:
        clean = supplied.strip()
        natural = clean.casefold()
        if not clean or natural in {"none", "empty", "someday", "no date"}:
            return None
        if natural in {"today", "now", "tonight", "urgent"}:
            return today.isoformat()
        if natural == "tomorrow":
            return (today + timedelta(days=1)).isoformat()
        return clean

    if re.search(r"\b(at some point|someday|one day|maybe someday)\b", lowered):
        return None
    if re.search(r"\b(today|now|tonight|urgent)\b", lowered):
        return today.isoformat()
    if "tomorrow" in lowered:
        return (today + timedelta(days=1)).isoformat()
    iso_date = re.search(r"\b\d{4}-\d{2}-\d{2}\b", message)
    if iso_date:
        return iso_date.group(0)
    return (today + timedelta(days=1)).isoformat()


def friendly_when(value: str | dict[str, str] | None, now: datetime) -> str:
    if value is None:
        return "no date"
    raw = value.get("start") if isinstance(value, dict) else value
    if not raw:
        return "no date"
    raw_date = raw[:10]
    if raw_date == now.date().isoformat():
        return "today"
    if raw_date == (now.date() + timedelta(days=1)).isoformat():
        return "tomorrow"
    return raw


class TaskFieldWriter:
    """Write optional task fields on top of Card 3's scoped TaskStore.

    The Notion path uses the adapter's already-compiled `set_page_property`
    operation after proving the page came from `list_tasks()`.  The adapter and
    its allowlist remain unchanged.
    """

    def __init__(self, task_store: TaskStore):
        self.task_store = task_store

    @staticmethod
    def _normalized(task_id: str) -> str:
        return task_id.replace("-", "").casefold()

    def _tasks_by_id(self) -> dict[str, Task]:
        return {
            self._normalized(task.id): task for task in self.task_store.list_tasks()
        }

    def _task(self, task_id: str) -> Task:
        task = self._tasks_by_id().get(self._normalized(task_id))
        if task is None:
            raise ValueError("Task is not in the configured task store")
        return task

    @staticmethod
    def _notion_value(field: str, value):
        if field == "when":
            return {"date": {"start": value}} if value else {"date": None}
        if field == "place":
            return {"select": {"name": value}} if value else {"select": None}
        if field == "minutes":
            return {"number": value}
        if field == "notes":
            return (
                {"rich_text": [{"type": "text", "text": {"content": value}}]}
                if value
                else {"rich_text": []}
            )
        raise ValueError(f"Unsupported task field: {field}")

    def update(
        self,
        task_id: str,
        *,
        when=_UNSET,
        place=_UNSET,
        minutes=_UNSET,
        notes=_UNSET,
    ) -> Task:
        changes = {
            key: value
            for key, value in {
                "when": when,
                "place": place,
                "minutes": minutes,
                "notes": notes,
            }.items()
            if value is not _UNSET
        }
        if not changes:
            return self._task(task_id)
        task = self._task(task_id)
        local_update = getattr(self.task_store, "update_task_fields", None)
        if callable(local_update):
            return local_update(task.id, **changes)

        client = getattr(self.task_store, "client", None)
        if client is None:
            raise TypeError("Task store cannot update optional task fields")
        names = {
            "when": "When",
            "place": "Place",
            "minutes": "Minutes",
            "notes": "Notes",
        }
        for field, value in changes.items():
            client.execute(
                "set_page_property",
                {
                    "page_id": task.id,
                    "name": names[field],
                    "value": self._notion_value(field, value),
                },
            )
            setattr(task, field, value)
        return task

    def set_plan_times(self, items: Iterable[dict]) -> list[Task]:
        """Set only `When`, validating every task before the first write."""
        items = list(items)
        tasks = self._tasks_by_id()
        resolved: list[tuple[Task, str]] = []
        for item in items:
            task = tasks.get(self._normalized(item["task_id"]))
            if task is None:
                raise ValueError("A planned task is no longer in the task store")
            resolved.append((task, item["when"]))

        local_update = getattr(self.task_store, "update_task_fields", None)
        if callable(local_update):
            return [local_update(task.id, when=when) for task, when in resolved]

        client = getattr(self.task_store, "client", None)
        if client is None:
            raise TypeError("Task store cannot schedule tasks")
        for task, when in resolved:
            client.execute(
                "set_page_property",
                {
                    "page_id": task.id,
                    "name": "When",
                    "value": self._notion_value("when", when),
                },
            )
            task.when = when
        return [task for task, _ in resolved]


class DayPlanner:
    """Build two felt-different, eight-hour plans from open place-matched tasks."""

    def __init__(
        self,
        task_store: TaskStore,
        *,
        clock: Callable[[], datetime] | None = None,
        day_minutes: int = DAY_MINUTES,
    ) -> None:
        self.task_store = task_store
        self.clock = clock
        self.day_minutes = day_minutes
        self.writer = TaskFieldWriter(task_store)

    def _open_recent(self) -> list[Task]:
        tasks = [task for task in self.task_store.list_tasks() if task.status != DONE]
        return tasks[-30:]

    def recent_places(self) -> list[str]:
        seen: list[str] = []
        for task in reversed(self._open_recent()):
            place = (task.place or "").strip()
            if place and place.casefold() != ANYWHERE.casefold() and place not in seen:
                seen.append(place)
        return [*seen, ANYWHERE]

    def default_place(self) -> str:
        places = [(task.place or "").strip() for task in self._open_recent()]
        places = [place for place in places if place]
        if not places:
            return ANYWHERE
        counts = Counter(places)
        highest = max(counts.values())
        tied = {place for place, count in counts.items() if count == highest}
        for place in reversed(places):
            if place in tied:
                return place
        return ANYWHERE

    @staticmethod
    def _duration(task: Task) -> int:
        if task.minutes is None:
            return DEFAULT_MINUTES
        return max(0, int(task.minutes))

    def _eligible(self, place: str) -> list[Task]:
        allowed = {place.casefold(), ANYWHERE.casefold()}
        return [
            task
            for task in self.task_store.list_tasks()
            if task.status != DONE
            and (task.place or ANYWHERE).casefold() in allowed
        ]

    def _fit_day(self, tasks: list[Task]) -> list[Task]:
        chosen: list[Task] = []
        used = 0
        for task in tasks:
            duration = self._duration(task)
            if used + duration <= self.day_minutes:
                chosen.append(task)
                used += duration
        return chosen

    def _schedule(self, tasks: list[Task], target: date) -> list[dict]:
        cursor = datetime.combine(target, DAY_START, tzinfo=JERUSALEM)
        items = []
        for task in tasks:
            duration = self._duration(task)
            items.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "minutes": duration,
                    "when": cursor.isoformat(timespec="minutes"),
                }
            )
            cursor += timedelta(minutes=duration)
        return items

    @staticmethod
    def _render_plan(label: str, subtitle: str, items: list[dict]) -> list[str]:
        lines = [f"Plan {label} \u2014 {subtitle}"]
        if not items:
            return [*lines, "No matching open tasks."]
        for item in items:
            start = item["when"][11:16]
            lines.append(f"{start} \u00b7 {item['title']} \u00b7 {item['minutes']} min")
        return lines

    def build(self, place: str | None = None) -> dict:
        now = local_now(self.clock)
        target = now.date() + timedelta(days=1)
        offered = self.recent_places()
        requested = (place or "").strip()
        known_place = next(
            (known for known in offered if requested.casefold() == known.casefold()),
            None,
        )
        chosen_place = known_place or self.default_place()
        fitted = self._fit_day(self._eligible(chosen_place))

        heavy = sorted(fitted, key=self._duration, reverse=True)
        light_sorted = sorted(fitted, key=self._duration)
        quick_count = min(2, max(1, len(light_sorted) // 3)) if light_sorted else 0
        light = light_sorted[:quick_count] + sorted(
            light_sorted[quick_count:], key=self._duration, reverse=True
        )
        plan_a = self._schedule(heavy, target)
        plan_b = self._schedule(light, target)
        same_order = [item["task_id"] for item in plan_a] == [
            item["task_id"] for item in plan_b
        ]

        if known_place is None:
            opening = (
                f"Where will you be tomorrow \u2014 {', '.join(offered)}?\n"
                f"I used {chosen_place} by default."
            )
        else:
            opening = f"Planning tomorrow for {chosen_place}."
        lines = [opening, ""]
        lines.extend(self._render_plan("A", "heavy first", plan_a))
        lines.append("")
        lines.extend(self._render_plan("B", "light first", plan_b))
        if same_order:
            lines.extend(
                ["", "These are nearly identical because the matching tasks do not offer a meaningful reorder."]
            )

        return {
            "plan_id": str(uuid.uuid4()),
            "date": target.isoformat(),
            "place": chosen_place,
            "plans": {"A": plan_a, "B": plan_b},
            "controls": [
                {"id": "A", "label": "Pick Plan A"},
                {"id": "B", "label": "Pick Plan B"},
            ],
            "similar": same_order,
            "text": "\n".join(lines),
        }

    def pick(self, sweep: dict, plan: str) -> list[Task]:
        if plan not in {"A", "B"}:
            raise ValueError("plan must be A or B")
        plans = sweep.get("plans") if isinstance(sweep, dict) else None
        if not isinstance(plans, dict) or plan not in plans:
            raise ValueError("No pending plan to pick")
        return self.writer.set_plan_times(plans[plan])


def next_jerusalem_daily(epoch: float, hour: int, minute: int = 0) -> float:
    """The next occurrence of hour:minute, Jerusalem local, strictly ahead."""
    now = datetime.fromtimestamp(epoch, JERUSALEM)
    at = time(hour, minute)
    candidate = datetime.combine(now.date(), at, tzinfo=JERUSALEM)
    if candidate <= now:
        candidate = datetime.combine(now.date() + timedelta(days=1), at, tzinfo=JERUSALEM)
    return candidate.timestamp()


def next_jerusalem_nine_pm(epoch: float) -> float:
    return next_jerusalem_daily(epoch, 21)


def nightly_due(epoch: float, last_run_at: float | None) -> bool:
    now = datetime.fromtimestamp(epoch, JERUSALEM)
    if now.hour < 21:
        return False
    if last_run_at is None:
        return True
    last = datetime.fromtimestamp(last_run_at, JERUSALEM)
    return last.date() < now.date()
