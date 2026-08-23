#!/usr/bin/env python3
"""Verify and smoke-test the single existing Notion tasks database.

No command accepts or prints a token or Notion database id. Both values are
read only from ~/.config/agentonomy/notion.env after mode and key validation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.notion_mcp import (  # noqa: E402
    STEADY_STATE_OPERATIONS,
    AdkNotionMcpClient,
    NotionConfig,
    _redact,
)
from app.notion_task_store import (  # noqa: E402
    DONE,
    IN_PROGRESS,
    NOT_STARTED,
    NotionTaskStore,
)

ENV_FILE = Path.home() / ".config" / "agentonomy" / "notion.env"
SMOKE_STATE_FILE = ROOT / "evidence" / ".notion-live-smoke-state.json"
EXPECTED_ENV_KEYS = frozenset({"NOTION_TOKEN", "NOTION_TASKS_DATABASE_ID"})
_SMOKE_MARKER = re.compile(r"^card3-[0-9a-f]{32}$")


def _assert_secret_file(path: Path = ENV_FILE) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError("Notion secret file is missing") from exc
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError("Notion secret path must be a regular file, not a link")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError("Notion secret file must have mode 0600")


def _read_env(path: Path = ENV_FILE) -> dict[str, str]:
    _assert_secret_file(path)
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError("Notion secret file contains a malformed line")
        key, value = line.split("=", 1)
        key = key.strip()
        if key in values:
            raise RuntimeError("Notion secret file contains a duplicate key")
        values[key] = value.strip()
    if set(values) != EXPECTED_ENV_KEYS:
        raise RuntimeError(
            "Notion secret file must contain exactly NOTION_TOKEN and "
            "NOTION_TASKS_DATABASE_ID"
        )
    return values


def _normalize_id(value: str) -> str:
    return value.replace("-", "").lower()


def _validate_isolation_result(data: Any, database_id: str) -> None:
    if not isinstance(data, dict):
        raise RuntimeError("Notion search returned malformed JSON")
    results = data.get("results")
    if not isinstance(results, list):
        raise RuntimeError("Notion search returned malformed results")
    if len(results) != 1:
        raise RuntimeError(
            "Isolation regression: search must return exactly one object"
        )
    if data.get("has_more") is not False:
        raise RuntimeError("Isolation regression: search must report has_more=false")
    only = results[0]
    parent = only.get("parent") if isinstance(only, dict) else None
    if (
        not isinstance(only, dict)
        or only.get("object") != "data_source"
        or not isinstance(parent, dict)
        or parent.get("type") != "database_id"
        or not isinstance(parent.get("database_id"), str)
        or _normalize_id(parent["database_id"]) != _normalize_id(database_id)
    ):
        raise RuntimeError(
            "Isolation regression: the sole search result is not the configured "
            "tasks database's data source"
        )


def isolation() -> None:
    values = _read_env()
    config = NotionConfig.from_env(values)
    request = urllib.request.Request(
        "https://api.notion.com/v1/search",
        data=b'{"page_size":100}',
        method="POST",
        headers={
            "Authorization": f"Bearer {config.token}",
            "Notion-Version": "2026-03-11",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError("Notion isolation request did not return HTTP 200")
            try:
                data = json.load(response)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("Notion isolation response was not JSON") from exc
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Notion isolation request returned HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Notion isolation request could not connect") from exc
    _validate_isolation_result(data, config.tasks_database_id)
    print("PASS: search returned only the configured tasks data source")


def discover() -> None:
    config = NotionConfig.from_env(_read_env())
    with AdkNotionMcpClient(config) as client:
        discovery = client.discovery
    if discovery.operations != frozenset(STEADY_STATE_OPERATIONS):
        raise RuntimeError("Steady-state operation discovery mismatch")
    print("PASS: MCP tools and the five-operation allowlist are exact")


def _write_smoke_state(marker: str, path: Path = SMOKE_STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"marker": marker}, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_smoke_state(path: Path = SMOKE_STATE_FILE) -> str | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError("Notion smoke state must be a regular mode-0600 file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Notion smoke state is malformed") from exc
    marker = data.get("marker") if isinstance(data, dict) else None
    if not isinstance(marker, str) or not _SMOKE_MARKER.fullmatch(marker):
        raise RuntimeError("Notion smoke state has an invalid marker")
    return marker


def _owned_by(marker: str, title: str) -> bool:
    return title.startswith(f"{marker} ")


def _archive_smoke_rows(store: NotionTaskStore, marker: str) -> None:
    rows = store.list_tasks()
    owned = [task for task in rows if _owned_by(marker, task.title)]
    for task in owned:
        store.client.execute("archive_page", {"page_id": task.id})
    remaining = store.list_tasks()
    if remaining:
        raise RuntimeError("Live smoke cleanup did not leave the board at zero rows")


def live_smoke(approved: bool, state_path: Path = SMOKE_STATE_FILE) -> None:
    if not approved:
        raise RuntimeError("Refusing live writes without --approved-live-tests")
    config = NotionConfig.from_env(_read_env())
    marker = _read_smoke_state(state_path)
    resumed = marker is not None
    if marker is None:
        marker = f"card3-{secrets.token_hex(16)}"
        _write_smoke_state(marker, state_path)

    store = NotionTaskStore(config)
    try:
        initial = store.list_tasks()
        if resumed:
            if any(not _owned_by(marker, task.title) for task in initial):
                raise RuntimeError(
                    "Cannot resume smoke cleanup while a non-smoke row exists"
                )
        elif initial:
            raise RuntimeError("Live smoke requires the board to start at zero rows")

        fields_title = f"{marker} six-property mapping"
        move_title = f"{marker} status move"
        renamed_title = f"{marker} renamed status move"
        names = {task.title: task for task in initial}

        fields_task = names.get(fields_title)
        if fields_task is None:
            fields_task = store.create_task(
                fields_title,
                NOT_STARTED,
                when="2099-01-01",
                place="Anywhere",
                minutes=5,
                notes=f"{marker} temporary smoke row",
            )
        if (
            fields_task.status != NOT_STARTED
            or fields_task.when != "2099-01-01"
            or fields_task.place != "Anywhere"
            or fields_task.minutes != 5
            or not fields_task.notes
        ):
            raise RuntimeError("Six-property task mapping was not confirmed")

        moving_task = names.get(move_title) or names.get(renamed_title)
        if moving_task is None:
            moving_task = store.create_task(move_title, IN_PROGRESS)
        if moving_task.title == move_title:
            moving_task = store.rename_task(moving_task.id, renamed_title)
        if moving_task.status == IN_PROGRESS:
            moving_task = store.move_task(moving_task.id, DONE)
        if moving_task.title != renamed_title or moving_task.status != DONE:
            raise RuntimeError("Rename or Status move was not confirmed")

        not_started = {task.id: task for task in store.list_tasks(NOT_STARTED)}
        done = {task.id: task for task in store.list_tasks(DONE)}
        if fields_task.id not in not_started or moving_task.id not in done:
            raise RuntimeError("Status-filtered queries did not return the smoke rows")
        remote_fields = not_started[fields_task.id]
        if (
            remote_fields.when != "2099-01-01"
            or remote_fields.place != "Anywhere"
            or remote_fields.minutes != 5
            or remote_fields.notes != f"{marker} temporary smoke row"
        ):
            raise RuntimeError("Queried row did not preserve all optional fields")
        if done[moving_task.id].title != renamed_title:
            raise RuntimeError("Queried row did not preserve its renamed Name")
    finally:
        try:
            _archive_smoke_rows(store, marker)
        finally:
            store.close()

    state_path.unlink(missing_ok=True)
    print(
        "PASS: created, renamed, moved, queried, and archived only synthetic "
        "rows; board row count is zero"
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("isolation", help="require exactly one searchable database")
    sub.add_parser("discover", help="verify the exact local MCP surface")
    smoke = sub.add_parser(
        "live-smoke", help="exercise task mappings and restore an empty board"
    )
    smoke.add_argument("--approved-live-tests", action="store_true")
    return result


def _safe_error(exc: Exception) -> str:
    secrets_to_hide: list[str] = []
    try:
        values = _read_env()
    except Exception:  # noqa: BLE001
        values = {}
    for key in EXPECTED_ENV_KEYS:
        value = values.get(key)
        if value:
            secrets_to_hide.append(value)
    return _redact(str(exc), *secrets_to_hide)


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "isolation":
            isolation()
        elif args.command == "discover":
            discover()
        elif args.command == "live-smoke":
            live_smoke(args.approved_live_tests)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {type(exc).__name__}: {_safe_error(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
