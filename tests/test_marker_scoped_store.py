from __future__ import annotations

import pytest

from app.task_store import FakeTaskStore
from tools.marker_scoped_task_store import MarkerScopedTaskStore


MARKER = "A16799E0-RC-20260823-01"


def test_marker_scope_hides_and_protects_unowned_rows():
    delegate = FakeTaskStore()
    existing = delegate.create_task(
        "Private existing row",
        place="Office",
        minutes=90,
        notes="Must remain untouched",
    )
    store = MarkerScopedTaskStore(delegate, MARKER)

    synthetic = store.create_task(
        "Call plumber",
        place="Anywhere",
        minutes=30,
        notes="remind me to call the plumber",
    )

    assert [task.id for task in store.list_tasks()] == [synthetic.id]
    assert MARKER in synthetic.notes
    with pytest.raises(ValueError, match="not owned"):
        store.move_task(existing.id, "Done")
    with pytest.raises(ValueError, match="not owned"):
        store.update_task_fields(existing.id, when="2099-01-01")

    store.update_task_fields(synthetic.id, when="2099-01-01")
    assert synthetic.when == "2099-01-01"
    assert existing.when is None
    assert existing.status == "Not started"


def test_marker_validation_fails_closed():
    with pytest.raises(ValueError, match="marker"):
        MarkerScopedTaskStore(FakeTaskStore(), "short")
