"""A test-only Notion guard that can see and mutate one synthetic marker.

The production app never constructs this wrapper. The live release-candidate
story uses it so planning and model tools cannot read or change the user's existing
row, even when the model asks to list every open task.
"""
from __future__ import annotations

import re

from app.task_planning import TaskFieldWriter
from app.task_store import Task, TaskStore


_MARKER = re.compile(r"^[A-Z0-9][A-Z0-9-]{15,79}$")


class MarkerScopedTaskStore(TaskStore):
    """Expose only rows carrying one explicit synthetic-test marker."""

    def __init__(self, delegate: TaskStore, marker: str) -> None:
        if not isinstance(marker, str) or _MARKER.fullmatch(marker) is None:
            raise ValueError(
                "marker must be 16-80 uppercase letters, digits, or hyphens"
            )
        self.delegate = delegate
        self.marker = marker
        self.marker_text = f"Synthetic acceptance marker: {marker}"

    @staticmethod
    def _normalized(task_id: str) -> str:
        return task_id.replace("-", "").casefold()

    def owns(self, task: Task) -> bool:
        return self.marker in task.title or self.marker in (task.notes or "")

    def list_tasks(self, lane: str | None = None) -> list[Task]:
        """Filter before any caller, model tool, or planner can observe rows."""
        return [task for task in self.delegate.list_tasks(lane) if self.owns(task)]

    def _owned_task(self, task_id: str) -> Task:
        target = self._normalized(task_id)
        matches = [
            task
            for task in self.list_tasks()
            if self._normalized(task.id) == target
        ]
        if len(matches) != 1:
            raise ValueError("Task is not owned by this synthetic acceptance run")
        return matches[0]

    def create_task(
        self,
        title: str,
        lane: str = "Not started",
        *,
        when: str | None = None,
        place: str | None = None,
        minutes: int | float | None = None,
        notes: str | None = None,
    ) -> Task:
        clean_notes = (notes or "").strip()
        marked_notes = (
            f"{clean_notes}\n\n{self.marker_text}" if clean_notes else self.marker_text
        )
        task = self.delegate.create_task(
            title,
            lane,
            when=when,
            place=place,
            minutes=minutes,
            notes=marked_notes,
        )
        if not self.owns(task):
            raise RuntimeError("Created row did not retain its acceptance marker")
        return task

    def rename_task(self, task_id: str, new_title: str) -> Task:
        task = self._owned_task(task_id)
        return self.delegate.rename_task(task.id, new_title)

    def move_task(self, task_id: str, to_lane: str) -> Task:
        task = self._owned_task(task_id)
        return self.delegate.move_task(task.id, to_lane)

    def update_task_fields(self, task_id: str, **changes) -> Task:
        task = self._owned_task(task_id)
        local_update = getattr(self.delegate, "update_task_fields", None)
        if callable(local_update):
            return local_update(task.id, **changes)
        return TaskFieldWriter(self.delegate).update(task.id, **changes)

    def archive_all_owned(self) -> int:
        """Archive only currently visible marker rows; never inspect row titles."""
        rows = self.list_tasks()
        client = getattr(self.delegate, "client", None)
        if client is None:
            raise TypeError("Wrapped task store does not expose archive_page")
        for task in rows:
            client.execute("archive_page", {"page_id": task.id})
        remaining = self.list_tasks()
        if remaining:
            raise RuntimeError("Synthetic marker rows remain after cleanup")
        return len(rows)

    def close(self) -> None:
        close = getattr(self.delegate, "close", None)
        if callable(close):
            close()
