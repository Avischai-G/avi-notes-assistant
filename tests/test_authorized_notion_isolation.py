"""Regression tests for Avi's authorized row-aware Notion isolation boundary."""

from __future__ import annotations

import pytest

from scripts.notion_board_setup import _validate_isolation_result


DATABASE_ID = "a" * 32
DATA_SOURCE_ID = "b" * 32


def data_source(*, source_id: str = DATA_SOURCE_ID, database_id: str = DATABASE_ID):
    return {
        "object": "data_source",
        "id": source_id,
        "parent": {"type": "database_id", "database_id": database_id},
    }


def page(*, source_id: str = DATA_SOURCE_ID, parent_type: str = "data_source_id"):
    return {
        "object": "page",
        "id": "c" * 32,
        "parent": {"type": parent_type, "data_source_id": source_id},
    }


def assert_rejected(results, *, has_more=False):
    with pytest.raises(RuntimeError, match="Isolation regression"):
        _validate_isolation_result(
            {"results": results, "has_more": has_more}, DATABASE_ID
        )


def test_accepts_configured_data_source_and_only_its_pages():
    _validate_isolation_result(
        {
            "results": [
                page(),
                data_source(),
                {**page(), "id": "d" * 32},
            ],
            "has_more": False,
        },
        DATABASE_ID,
    )


def test_accepts_data_source_whose_own_id_matches_configured_id():
    _validate_isolation_result(
        {
            "results": [
                {
                    "object": "data_source",
                    "id": DATABASE_ID,
                    "parent": {"type": "workspace", "workspace": True},
                },
                page(source_id=DATABASE_ID),
            ],
            "has_more": False,
        },
        DATABASE_ID,
    )


@pytest.mark.parametrize(
    "results,has_more",
    [
        ([], False),
        ([data_source(), data_source(source_id="e" * 32)], False),
        ([data_source(), page(source_id="e" * 32)], False),
        ([data_source(), page(parent_type="database_id")], False),
        (
            [
                data_source(),
                {
                    "object": "database",
                    "id": DATABASE_ID,
                    "parent": {"type": "workspace", "workspace": True},
                },
            ],
            False,
        ),
        ([data_source(), "malformed"], False),
        ([data_source(database_id="e" * 32)], False),
        ([data_source()], True),
    ],
)
def test_rejects_any_result_outside_the_authorized_boundary(results, has_more):
    assert_rejected(results, has_more=has_more)
