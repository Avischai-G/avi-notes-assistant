"""Private learning-event storage and aggregate-only calendar summaries.

The full event records in this module are for in-process agent use. Browser routes
must return only :func:`aggregate_learning_periods` output.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
from typing import Callable, Iterable, Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


LearningAction = Literal["created", "updated", "dreamed", "consolidated"]
Period = Literal["day", "week", "month"]
_ACTIONS = {"created", "updated", "dreamed", "consolidated"}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("learning-event timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class LearningEvent:
    """One private record of a knowledge write."""

    timestamp: datetime
    path: str
    action: LearningAction
    summary: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", _as_utc(self.timestamp))
        if self.action not in _ACTIONS:
            raise ValueError(f"unsupported learning action: {self.action}")
        if not self.path or self.path.startswith("/") or ".." in self.path.split("/"):
            raise ValueError("learning-event path must be a safe logical path")
        summary = self.summary.strip()
        if not summary:
            raise ValueError("learning-event summary must not be empty")
        if len(summary) > 240:
            raise ValueError("learning-event summary must be 240 characters or fewer")
        object.__setattr__(self, "summary", summary)

    def to_firestore(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "path": self.path,
            "action": self.action,
            "summary": self.summary,
        }

    def to_agent_payload(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
            "path": self.path,
            "action": self.action,
            "summary": self.summary,
        }

    @classmethod
    def from_firestore(cls, value: dict) -> "LearningEvent":
        timestamp = value.get("timestamp")
        if hasattr(timestamp, "to_datetime"):
            timestamp = timestamp.to_datetime()
        if not isinstance(timestamp, datetime):
            raise ValueError("Firestore learning event has no datetime timestamp")
        return cls(
            timestamp=timestamp,
            path=str(value.get("path", "")),
            action=value.get("action"),
            summary=str(value.get("summary", "")),
        )


class LearningEventStore(Protocol):
    def append(self, event: LearningEvent) -> None: ...

    def list_all(self) -> list[LearningEvent]: ...


class LocalLearningEventStore:
    """Deterministic in-memory metadata store for local development and tests."""

    def __init__(self, events: Iterable[LearningEvent] = ()) -> None:
        self._events = list(events)

    def append(self, event: LearningEvent) -> None:
        self._events.append(event)

    def list_all(self) -> list[LearningEvent]:
        return sorted(self._events, key=lambda event: event.timestamp)


class FirestoreLearningEventStore:
    """Firestore metadata adapter; file bodies never enter Firestore."""

    COLLECTION = "knowledge_learning_events"

    def __init__(self, db, collection: str = COLLECTION) -> None:
        self._collection = db.collection(collection)

    def append(self, event: LearningEvent) -> None:
        self._collection.add(event.to_firestore())

    def list_all(self) -> list[LearningEvent]:
        events = [
            LearningEvent.from_firestore(document.to_dict())
            for document in self._collection.stream()
        ]
        return sorted(events, key=lambda event: event.timestamp)


def _week_start_for(timezone_name: str, requested_week_start: int) -> int:
    """Return Python's weekday index (Monday=0, Sunday=6).

    Israel's locale week is explicitly Sunday-first. Other browser locales supply
    their resolved first day through ``requested_week_start``.
    """

    if timezone_name == "Asia/Jerusalem":
        return 6
    if requested_week_start not in range(7):
        raise ValueError("week_start must be an integer from 0 through 6")
    return requested_week_start


def _period_start(
    period: Period,
    local_now: datetime,
    week_start: int,
) -> datetime:
    local_midnight = datetime.combine(local_now.date(), time.min, local_now.tzinfo)
    if period == "day":
        return local_midnight
    if period == "week":
        days_since_start = (local_now.weekday() - week_start) % 7
        return local_midnight - timedelta(days=days_since_start)
    if period == "month":
        return local_midnight.replace(day=1)
    raise ValueError(f"unsupported learning period: {period}")


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def _daily_summary(events: list[LearningEvent]) -> str:
    categories: Counter[str] = Counter()
    for event in events:
        if event.path.startswith("skills/") and event.action in {"created", "updated"}:
            categories["skill"] += 1
        elif event.path.startswith("rules/") and event.action in {"created", "updated"}:
            categories["rule"] += 1
        elif event.action == "consolidated":
            categories["consolidation"] += 1
        elif event.action == "dreamed":
            categories["observation"] += 1
        else:
            categories["change"] += 1

    parts: list[str] = []
    labels = (
        ("skill", "skill changed", "skills changed"),
        ("rule", "rule changed", "rules changed"),
        ("consolidation", "dream consolidated", "dreams consolidated"),
        ("observation", "observation captured", "observations captured"),
        ("change", "other change", "other changes"),
    )
    for key, singular, plural in labels:
        if categories[key]:
            parts.append(_plural(categories[key], singular, plural))
    return " · ".join(parts)


def aggregate_learning_periods(
    events: Iterable[LearningEvent],
    *,
    now: datetime,
    timezone_name: str,
    week_start: int = 0,
) -> dict:
    """Compute day/week/month aggregates from one immutable event snapshot."""

    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown browser timezone: {timezone_name}") from exc

    now_utc = _as_utc(now)
    local_now = now_utc.astimezone(zone)
    resolved_week_start = _week_start_for(timezone_name, week_start)
    snapshot = tuple(sorted(events, key=lambda event: event.timestamp))
    periods: dict[str, dict] = {}

    for period in ("day", "week", "month"):
        local_start = _period_start(period, local_now, resolved_week_start)
        start_utc = local_start.astimezone(timezone.utc)
        selected = [
            event
            for event in snapshot
            if start_utc <= event.timestamp <= now_utc
        ]
        daily: dict[str, list[LearningEvent]] = defaultdict(list)
        for event in selected:
            local_day = event.timestamp.astimezone(zone).date().isoformat()
            daily[local_day].append(event)

        periods[period] = {
            "total_changes": len(selected),
            "skills_created_updated": sum(
                event.path.startswith("skills/")
                and event.action in {"created", "updated"}
                for event in selected
            ),
            "rules_changed": sum(
                event.path.startswith("rules/")
                and event.action in {"created", "updated"}
                for event in selected
            ),
            "dreams_consolidated": sum(
                event.action == "consolidated" for event in selected
            ),
            "daily_summaries": [
                {"date": day, "summary": _daily_summary(daily[day])}
                for day in sorted(daily, reverse=True)
            ],
            "window_start": local_start.isoformat(),
        }

    return {
        "timezone": timezone_name,
        "week_start": resolved_week_start,
        "generated_at": now_utc.isoformat().replace("+00:00", "Z"),
        "periods": periods,
    }


Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
