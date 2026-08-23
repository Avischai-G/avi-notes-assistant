"""Fail-closed TaskStore for the one configured Notion tasks database."""

from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Any

from app.notion_mcp import AdkNotionMcpClient, NotionConfig, NotionMcpClient
from app.task_store import Task, TaskStore

NAME = "Name"
STATUS = "Status"
WHEN = "When"
PLACE = "Place"
MINUTES = "Minutes"
NOTES = "Notes"

NOT_STARTED = "Not started"
IN_PROGRESS = "In progress"
DONE = "Done"
STATUSES = frozenset({NOT_STARTED, IN_PROGRESS, DONE})


def _text(
    value: str,
    field: str,
    *,
    max_length: int = 2000,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    clean = value.strip()
    if not clean and not allow_empty:
        raise ValueError(f"{field} must be non-empty")
    if len(clean) > max_length:
        raise ValueError(f"{field} must be at most {max_length} characters")
    return clean


def _status(value: str) -> str:
    if value not in STATUSES:
        raise ValueError(
            "status must be exactly 'Not started', 'In progress', or 'Done'"
        )
    return value


def _when(value: str | None) -> str | None:
    if value is None:
        return None
    clean = _text(value, "when", max_length=100)
    try:
        datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("when must be an ISO-8601 date or datetime") from exc
    return clean


def _place(value: str | None) -> str | None:
    if value is None:
        return None
    # Notion permits a new select option name here; intentionally do not limit
    # this to the four options that currently exist in the fixed schema.
    return _text(value, "place", max_length=100)


def _minutes(value: int | float | None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("minutes must be a number")
    if not math.isfinite(value) or value < 0:
        raise ValueError("minutes must be finite and non-negative")
    return value


def _notes(value: str | None) -> str:
    if value is None:
        return ""
    return _text(value, "notes", allow_empty=True)


def _normalized_id(value: str) -> str:
    return value.replace("-", "").lower()


class NotionTaskStore(TaskStore):
    """Query and mutate rows only inside `NOTION_TASKS_DATABASE_ID`."""

    def __init__(
        self,
        config: NotionConfig,
        client: NotionMcpClient | None = None,
    ) -> None:
        self.config = config
        self.client = client or AdkNotionMcpClient(config)

    @classmethod
    def from_env(cls) -> NotionTaskStore:
        return cls(NotionConfig.from_env())

    def _task_from_page(self, page: Any) -> Task:
        if not isinstance(page, dict) or not isinstance(page.get("id"), str):
            raise RuntimeError("Notion MCP returned a malformed task row")
        title = page.get("title")
        properties = page.get("properties")
        if not isinstance(title, str) or not title.strip():
            raise RuntimeError("Notion task has no Name title")
        if properties is None:
            properties = {}
        if not isinstance(properties, dict):
            raise RuntimeError("Notion task properties are malformed")

        status = properties.get(STATUS)
        if status not in STATUSES:
            raise RuntimeError("Notion task has an unset or unexpected Status")

        when = properties.get(WHEN)
        if when is not None and not isinstance(when, (str, dict)):
            raise RuntimeError("Notion task has a malformed When value")
        if isinstance(when, dict):
            if not isinstance(when.get("start"), str) or any(
                key not in {"start", "end"} for key in when
            ):
                raise RuntimeError("Notion task has a malformed When range")
            if "end" in when and not isinstance(when["end"], str):
                raise RuntimeError("Notion task has a malformed When range")

        place = properties.get(PLACE)
        if place is not None and not isinstance(place, str):
            raise RuntimeError("Notion task has a malformed Place value")
        minutes = properties.get(MINUTES)
        if minutes is not None and (
            isinstance(minutes, bool) or not isinstance(minutes, (int, float))
        ):
            raise RuntimeError("Notion task has a malformed Minutes value")
        notes = properties.get(NOTES, "")
        if not isinstance(notes, str):
            raise RuntimeError("Notion task has a malformed Notes value")

        return Task(
            id=page["id"],
            title=title.strip(),
            lane=status,
            created_at=0.0,
            updated_at=0.0,
            when=when,
            place=place,
            minutes=minutes,
            notes=notes,
        )

    def _get_task(self, task_id: str) -> Task:
        target = _normalized_id(_text(task_id, "task_id", max_length=64))
        matches = [
            task for task in self.list_tasks() if _normalized_id(task.id) == target
        ]
        if len(matches) != 1:
            raise ValueError("Task is not a row in the configured Notion database")
        return matches[0]

    def list_tasks(self, lane: str | None = None) -> list[Task]:
        payload: dict[str, Any] = {
            "database_id": self.config.tasks_database_id,
            "paginate": True,
            "page_limit": 1000,
            "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
        }
        if lane is not None:
            payload["filter"] = {
                "property": STATUS,
                "status": {"equals": _status(lane)},
            }
        data = self.client.execute("query_database", payload)
        rows = data.get("results") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError("Notion MCP returned a malformed task query")
        if data.get("truncated") is True:
            raise RuntimeError("Notion task query exceeded the 1000-row safety limit")
        tasks = [self._task_from_page(row) for row in rows]
        if lane is not None and any(task.status != lane for task in tasks):
            raise RuntimeError("Notion MCP returned a task with the wrong Status")
        return tasks

    def create_task(
        self,
        title: str,
        lane: str = NOT_STARTED,
        *,
        when: str | None = None,
        place: str | None = None,
        minutes: int | float | None = None,
        notes: str | None = None,
    ) -> Task:
        clean_title = _text(title, "title")
        clean_status = _status(lane)
        clean_when = _when(when)
        clean_place = _place(place)
        clean_minutes = _minutes(minutes)
        clean_notes = _notes(notes)

        properties: dict[str, Any] = {
            NAME: {"title": [{"type": "text", "text": {"content": clean_title}}]},
            STATUS: {"status": {"name": clean_status}},
        }
        if clean_when is not None:
            properties[WHEN] = {"date": {"start": clean_when}}
        if clean_place is not None:
            properties[PLACE] = {"select": {"name": clean_place}}
        if clean_minutes is not None:
            properties[MINUTES] = {"number": clean_minutes}
        if clean_notes:
            properties[NOTES] = {
                "rich_text": [{"type": "text", "text": {"content": clean_notes}}]
            }

        data = self.client.execute(
            "create_page",
            {
                "parent": {
                    "type": "database_id",
                    "database_id": self.config.tasks_database_id,
                },
                "properties": properties,
            },
        )
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            raise RuntimeError("Notion MCP returned a malformed created task")
        now = time.time()
        return Task(
            id=data["id"],
            title=clean_title,
            lane=clean_status,
            created_at=now,
            updated_at=now,
            when=clean_when,
            place=clean_place,
            minutes=clean_minutes,
            notes=clean_notes,
        )

    def rename_task(self, task_id: str, new_title: str) -> Task:
        existing = self._get_task(task_id)
        clean_title = _text(new_title, "new_title")
        self.client.execute(
            "set_page_title", {"page_id": existing.id, "title": clean_title}
        )
        existing.title = clean_title
        existing.updated_at = time.time()
        return existing

    def move_task(self, task_id: str, to_lane: str) -> Task:
        existing = self._get_task(task_id)
        clean_status = _status(to_lane)
        self.client.execute(
            "set_page_property",
            {
                "page_id": existing.id,
                "name": STATUS,
                "value": {"status": {"name": clean_status}},
            },
        )
        existing.status = clean_status
        existing.updated_at = time.time()
        return existing

    def close(self) -> None:
        self.client.close()
