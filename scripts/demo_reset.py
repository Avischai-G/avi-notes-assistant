#!/usr/bin/env python3
"""Prepare or remove only the synthetic Notion rows used in the demo.

This is intentionally not a general board reset. It cannot see rows without
the supplied marker through its guarded store, and cleanup archives marker
rows only. Both commands are outward writes and require live-test approval.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.notion_task_store import NotionTaskStore
from scripts.notion_board_setup import _read_env
from tools.marker_scoped_task_store import MarkerScopedTaskStore


ENV_FILE = Path.home() / ".config" / "agentonomy" / "notion.env"


def load_notion_environment(path: Path = ENV_FILE) -> None:
    """Load the two required values without displaying either one."""
    os.environ.update(_read_env(path))


def _open(marker: str) -> MarkerScopedTaskStore:
    load_notion_environment()
    return MarkerScopedTaskStore(NotionTaskStore.from_env(), marker)


def prepare(marker: str) -> None:
    store = _open(marker)
    try:
        if store.list_tasks():
            raise RuntimeError(
                "This marker already owns rows; clean it up before preparing again"
            )
        try:
            store.create_task(
                f"[{marker}] Draft release outline",
                place="Office",
                minutes=180,
                notes="Synthetic planning fixture only.",
            )
            store.create_task(
                f"[{marker}] Send synthetic update",
                place="Anywhere",
                minutes=15,
                notes="Synthetic planning fixture only.",
            )
        except Exception:
            store.archive_all_owned()
            raise
        print(f"PREPARED marker={marker} synthetic_rows=2")
    finally:
        store.close()


def cleanup(marker: str) -> None:
    store = _open(marker)
    try:
        archived = store.archive_all_owned()
        print(f"CLEAN marker={marker} archived_marker_rows={archived} remaining_marker_rows=0")
    finally:
        store.close()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Marker-scoped synthetic demo rows; never a whole-board reset"
    )
    result.add_argument("command", choices=("prepare", "cleanup"))
    result.add_argument("--marker", required=True)
    result.add_argument(
        "--approved-live-test",
        action="store_true",
        help="confirm that the exact live acceptance write set was approved",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.approved_live_test:
        raise RuntimeError("Refusing persistent Notion writes without approval flag")
    if args.command == "prepare":
        prepare(args.marker)
    else:
        cleanup(args.marker)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
