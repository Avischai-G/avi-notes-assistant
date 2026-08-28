"""Small, deterministic policy: date inference, board review, triggers."""
from __future__ import annotations

from datetime import datetime, time, timedelta
import re
from typing import Callable
from zoneinfo import ZoneInfo

from app.task_store import Task, TaskStore


JERUSALEM = ZoneInfo("Asia/Jerusalem")
DONE = "Done"
ANYWHERE = "Anywhere"
DEFAULT_MINUTES = 30
DAY_MINUTES = 8 * 60
DAY_START = time(9, 0)
_UNSET = object()


def local_now(clock: Callable[[], datetime] | None = None, tz=None) -> datetime:
    zone = tz or JERUSALEM
    value = clock() if clock else datetime.now(zone)
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone)
    return value.astimezone(zone)


def tomorrow_iso(clock: Callable[[], datetime] | None = None, tz=None) -> str:
    return (local_now(clock, tz).date() + timedelta(days=1)).isoformat()


def infer_when(
    message: str,
    supplied: str | None,
    clock: Callable[[], datetime] | None = None,
    tz=None,
) -> str | None:
    """Resolve the assistant's date defaults in the user's local time."""
    today = local_now(clock, tz).date()
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
    # No date was named, so the task gets none. A guessed "tomorrow" reads as a
    # commitment the user never made.
    return None


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
        has_column = getattr(self.task_store, "has_column", None)
        for field, value in changes.items():
            # A board edited by hand may have no Notes column; naming it would
            # make Notion reject the write outright.
            if field == "notes" and has_column is not None and not has_column("Notes"):
                continue
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


def recent_places(task_store: TaskStore, limit: int = 30) -> list[str]:
    """Place values already on the board, newest first, for the prompt hint."""
    seen: list[str] = []
    tasks = [task for task in task_store.list_tasks() if task.status != DONE]
    for task in reversed(tasks[-limit:]):
        place = (task.place or "").strip()
        if place and place not in seen:
            seen.append(place)
    return seen


WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
FREQUENCIES = ("hourly", "daily", "weekly")


def next_trigger(
    frequency: str,
    epoch: float,
    *,
    hour: int = 9,
    minute: int = 0,
    weekday: int = 0,
    tz=None,
) -> float:
    """The next moment a trigger fires, in the trigger's own local zone,
    strictly after `epoch`.

    Note: wall-clock arithmetic, so the one run that straddles a DST change
    keeps its stated hour and lands an hour off in absolute terms. That is the
    right trade for a once-a-year shift on a personal board.
    """
    zone = tz or JERUSALEM
    now = datetime.fromtimestamp(epoch, zone)
    if frequency == "hourly":
        candidate = now.replace(minute=minute, second=0, microsecond=0)
        step = timedelta(hours=1)
    else:
        candidate = datetime.combine(now.date(), time(hour, minute), tzinfo=zone)
        if frequency == "weekly":
            candidate += timedelta(days=(weekday - candidate.weekday()) % 7)
            step = timedelta(days=7)
        else:
            step = timedelta(days=1)
    return (candidate if candidate > now else candidate + step).timestamp()


def describe_trigger(frequency: str, hour: int, minute: int, weekday: int) -> str:
    """The one human sentence for a trigger, so the UI never formats its own."""
    if frequency == "hourly":
        return f"Hourly at :{minute:02d}"
    if frequency == "weekly":
        return f"Weekly on {WEEKDAYS[weekday]} at {hour:02d}:{minute:02d}"
    return f"Daily at {hour:02d}:{minute:02d}"
