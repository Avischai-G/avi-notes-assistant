"""Task board store interface.

Production uses Notion MCP (Card 3).
For now, use a deterministic fake that records all operations for testing.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal
import uuid


@dataclass
class Task:
    """A single task on the board."""
    id: str
    title: str
    lane: Literal["what to do today", "what to not do today"]
    created_at: float
    updated_at: float


class TaskStore:
    """Interface for querying and mutating tasks."""

    def list_tasks(self, lane: str | None = None) -> list[Task]:
        """List all tasks, optionally filtered by lane."""
        raise NotImplementedError

    def create_task(self, title: str, lane: str = "what to not do today") -> Task:
        """Create a new task."""
        raise NotImplementedError

    def rename_task(self, task_id: str, new_title: str) -> Task:
        """Rename a task."""
        raise NotImplementedError

    def move_task(self, task_id: str, to_lane: str) -> Task:
        """Move a task to a different lane."""
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

    def create_task(self, title: str, lane: str = "what to not do today") -> Task:
        import time
        task = Task(
            id=str(uuid.uuid4()),
            title=title,
            lane=lane,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.tasks[task.id] = task
        self.operations.append({
            "action": "create",
            "task_id": task.id,
            "title": title,
            "lane": lane,
        })
        return task

    def rename_task(self, task_id: str, new_title: str) -> Task:
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        import time
        task = self.tasks[task_id]
        task.title = new_title
        task.updated_at = time.time()
        self.operations.append({
            "action": "rename",
            "task_id": task_id,
            "new_title": new_title,
        })
        return task

    def move_task(self, task_id: str, to_lane: str) -> Task:
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        import time
        task = self.tasks[task_id]
        task.lane = to_lane
        task.updated_at = time.time()
        self.operations.append({
            "action": "move",
            "task_id": task_id,
            "from_lane": task.lane,
            "to_lane": to_lane,
        })
        return task
