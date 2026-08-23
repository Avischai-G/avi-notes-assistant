"""Task board store interface and deterministic local test store."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass
class Task:
    """A single task on the board."""

    id: str
    title: str
    lane: str
    created_at: float
    updated_at: float
    when: str | dict[str, str] | None = None
    place: str | None = None
    minutes: int | float | None = None
    notes: str = ""

    @property
    def status(self) -> str:
        """Expose the product's Status field over the frozen adapter shape."""
        return self.lane

    @status.setter
    def status(self, value: str) -> None:
        self.lane = value


class TaskStore:
    """Interface for querying and mutating tasks."""

    def list_tasks(self, lane: str | None = None) -> list[Task]:
        """List all tasks, optionally filtered by Status."""
        raise NotImplementedError

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
        """Create a new task."""
        raise NotImplementedError

    def rename_task(self, task_id: str, new_title: str) -> Task:
        """Rename a task."""
        raise NotImplementedError

    def move_task(self, task_id: str, to_lane: str) -> Task:
        """Set the task's Status."""
        raise NotImplementedError


class FakeTaskStore(TaskStore):
    """Deterministic fake for testing. Records all operations for verification."""

    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self.operations: list[dict] = []  # For testing

    def list_tasks(self, lane: str | None = None) -> list[Task]:
        tasks = list(self.tasks.values())
        if lane:
            tasks = [t for t in tasks if t.lane == lane]
        return sorted(tasks, key=lambda t: t.created_at)

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
        import time

        task = Task(
            id=str(uuid.uuid4()),
            title=title,
            lane=lane,
            created_at=time.time(),
            updated_at=time.time(),
            when=when,
            place=place,
            minutes=minutes,
            notes=notes or "",
        )
        self.tasks[task.id] = task
        self.operations.append(
            {
                "action": "create",
                "task_id": task.id,
                "title": title,
                "lane": lane,
                "when": when,
                "place": place,
                "minutes": minutes,
                "notes": notes or "",
            }
        )
        return task

    def update_task_fields(self, task_id: str, **changes) -> Task:
        """Update only named fields; used by planning tests and local chat."""
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        allowed = {"when", "place", "minutes", "notes"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unsupported task fields: {sorted(unknown)}")
        import time

        task = self.tasks[task_id]
        for field, value in changes.items():
            setattr(task, field, value)
        task.updated_at = time.time()
        self.operations.append(
            {"action": "update_fields", "task_id": task_id, "changes": changes}
        )
        return task

    def rename_task(self, task_id: str, new_title: str) -> Task:
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        import time

        task = self.tasks[task_id]
        task.title = new_title
        task.updated_at = time.time()
        self.operations.append(
            {
                "action": "rename",
                "task_id": task_id,
                "new_title": new_title,
            }
        )
        return task

    def move_task(self, task_id: str, to_lane: str) -> Task:
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        import time

        task = self.tasks[task_id]
        from_lane = task.lane
        task.lane = to_lane
        task.updated_at = time.time()
        self.operations.append(
            {
                "action": "move",
                "task_id": task_id,
                "from_lane": from_lane,
                "to_lane": to_lane,
            }
        )
        return task
