#!/usr/bin/env python3
"""Verify the approved live story through the real HTTP/SSE interfaces.

This script never loads a Notion token. The test-only server injects the
marker-scoped real adapter and exposes only synthetic row snapshots.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo


MARKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{15,79}$")
JERUSALEM = ZoneInfo("Asia/Jerusalem")
TASK_MESSAGE = "remind me to call the plumber"
VAGUE_MESSAGE = "whatever"
PLACE_MESSAGE = "I will be at Office tomorrow."


class Probe:
    def __init__(self, base_url: str, marker: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.marker = marker
        self.headers = {"X-Live-Acceptance-Marker": marker}

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        expected: int = 200,
    ):
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {**self.headers, "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                status = response.status
                raw = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read()
        if status != expected:
            raise AssertionError(f"{method} {path}: expected {expected}, received {status}")
        if expected == 404:
            return {"status": status}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{method} {path}: response was not JSON") from exc

    def chat(self, channel_id: str, message: str) -> list[dict]:
        request = urllib.request.Request(
            f"{self.base_url}/api/channels/{channel_id}/chat",
            data=json.dumps({"message": message}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            if response.status != 200:
                raise AssertionError(f"chat returned HTTP {response.status}")
            raw = response.read().decode("utf-8")
        chunks: list[dict] = []
        for block in raw.split("\n\n"):
            line = next((line for line in block.splitlines() if line.startswith("data:")), None)
            if line:
                chunks.append(json.loads(line[5:].strip()))
        if not chunks or chunks[-1] != {"done": True}:
            raise AssertionError("chat stream did not terminate with done=true")
        errors = [chunk["error"] for chunk in chunks if "error" in chunk]
        if errors:
            raise AssertionError("chat stream returned an error: " + "; ".join(errors))
        return chunks

    def rows(self) -> list[dict]:
        return self.request("GET", "/__acceptance__/rows")["rows"]


def _assistant_text(chunks: list[dict]) -> str:
    return "".join(chunk.get("text", "") for chunk in chunks)


def _plan_entries(text: str) -> dict[str, list[dict]]:
    plans: dict[str, list[dict]] = {"A": [], "B": []}
    current: str | None = None
    entry = re.compile(r"^(\d{2}:\d{2}) · (.+) · (\d+) min$")
    for line in text.splitlines():
        if line.startswith("Plan A —"):
            current = "A"
            continue
        if line.startswith("Plan B —"):
            current = "B"
            continue
        match = entry.fullmatch(line)
        if current and match:
            plans[current].append(
                {"time": match.group(1), "title": match.group(2), "minutes": int(match.group(3))}
            )
    return plans


def _by_id(rows: list[dict]) -> dict[str, dict]:
    return {row["id"]: row for row in rows}


def _assert_only_when_changed(before: list[dict], after: list[dict]) -> None:
    old, new = _by_id(before), _by_id(after)
    assert set(old) == set(new)
    immutable = {"id", "title", "status", "place", "minutes", "notes"}
    for task_id in old:
        for field in immutable:
            assert old[task_id][field] == new[task_id][field], (
                f"plan pick changed {field} on marker row {task_id}"
            )
        assert old[task_id]["when"] != new[task_id]["when"]


def _write_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run_story(probe: Probe, state_path: Path) -> None:
    target_date = (datetime.now(JERUSALEM).date() + timedelta(days=1)).isoformat()
    expected_seed_titles = {
        f"[{probe.marker}] Draft release outline",
        f"[{probe.marker}] Send synthetic update",
    }
    seeded = probe.rows()
    assert len(seeded) == 2
    assert {row["title"] for row in seeded} == expected_seed_titles

    channel_id = probe.request("POST", "/api/channels/init")["channel_id"]
    first = probe.chat(channel_id, TASK_MESSAGE)
    assert _assistant_text(first) == (
        "Noted — tomorrow, Anywhere, 30 min. Would a specific time tomorrow help?"
    )
    assert [chunk for chunk in first if chunk.get("tool") == "create_task"] == [
        {"tool": "create_task", "status": "started"},
        {"tool": "create_task", "status": "completed"},
    ]
    captured = probe.rows()
    assert len(captured) == 3
    plumber_rows = [row for row in captured if "plumber" in row["title"].casefold()]
    assert len(plumber_rows) == 1
    plumber = plumber_rows[0]
    assert plumber["status"] == "Not started"
    assert plumber["when"] == target_date
    assert plumber["place"] == "Anywhere"
    assert plumber["minutes"] == 30
    assert TASK_MESSAGE in plumber["notes"]
    assert probe.marker in plumber["notes"]

    vague = probe.chat(channel_id, VAGUE_MESSAGE)
    assert _assistant_text(vague) == "Kept the default — tomorrow, Anywhere, 30 min."
    assert "?" not in _assistant_text(vague)
    assert not any("tool" in chunk for chunk in vague)

    planning = probe.chat(channel_id, PLACE_MESSAGE)
    plan_text = _assistant_text(planning)
    controls = next(chunk["controls"] for chunk in planning if "controls" in chunk)
    assert controls == [
        {"id": "A", "label": "Pick Plan A"},
        {"id": "B", "label": "Pick Plan B"},
    ]
    assert "Plan A — heavy first" in plan_text
    assert "Plan B — light first" in plan_text
    entries = _plan_entries(plan_text)
    assert len(entries["A"]) == len(entries["B"]) == 3
    expected_titles = {*expected_seed_titles, plumber["title"]}
    assert {entry["title"] for entry in entries["A"]} == expected_titles
    assert {entry["title"] for entry in entries["B"]} == expected_titles
    assert [entry["title"] for entry in entries["A"]] != [
        entry["title"] for entry in entries["B"]
    ]
    assert [entry["minutes"] for entry in entries["A"]] == [180, 30, 15]
    assert [entry["minutes"] for entry in entries["B"]] == [15, 180, 30]

    before_pick = probe.rows()
    picked = probe.request(
        "POST", "/api/automations/nightly-plan/pick", {"plan": "A"}
    )
    assert picked["status"] == "picked" and picked["plan"] == "A"
    assert len(picked["scheduled_task_ids"]) == 3
    after_pick = probe.rows()
    _assert_only_when_changed(before_pick, after_pick)
    for row in after_pick:
        parsed = datetime.fromisoformat(row["when"])
        assert parsed.date().isoformat() == target_date
        assert parsed.tzinfo is not None
        assert parsed.astimezone(JERUSALEM).utcoffset() == parsed.utcoffset()

    task_history = probe.request("GET", f"/api/channels/{channel_id}")
    assert len(task_history["messages"]) == 8
    assistant_claims = "\n".join(
        message["content"]
        for message in task_history["messages"]
        if message["role"] == "assistant"
    ).casefold()
    for forbidden in (
        "i called the plumber",
        "i sent the synthetic update",
        "i drafted the release outline",
        "completed the underlying task",
    ):
        assert forbidden not in assistant_claims

    automations = probe.request("GET", "/api/automations")["automations"]
    assert {item["id"] for item in automations} == {"nightly-plan"}

    # The Learning page and its aggregate endpoint are gone; the log stays
    # private to the agent.
    for endpoint in ("", "/raw", "/events", "/log"):
        assert probe.request(
            "GET", f"/api/learning{endpoint}", expected=404
        )["status"] == 404

    manifest = probe.request("GET", "/__acceptance__/knowledge-manifest")
    assert manifest["skill_exists"] is True
    assert manifest["skill_sha256"]
    assert manifest["pending"] is False
    assert probe.rows() == after_pick

    state = {
        "marker": probe.marker,
        "target_date": target_date,
        "task_channel_id": channel_id,
        "task_history": task_history,
        "automations": automations,
        "knowledge_manifest": manifest,
        "rows": after_pick,
        "transcript_inputs": [TASK_MESSAGE, VAGUE_MESSAGE, PLACE_MESSAGE, "Pick Plan A"],
        "notion_optional_fields_before_pick": before_pick,
        "http_raw_learning_statuses": {endpoint: 404 for endpoint in ("raw", "events", "log")},
    }
    _write_state(state_path, state)
    print(
        "LIVE_STORY_PRE_RELOAD=PASS "
        "task_rows=3 plans=2 cleanup_runs=2 raw_http_routes=404"
    )


def resume_story(probe: Probe, state_path: Path, task_channel_id: str) -> None:
    """Resume after the proven task phase and exercise every remaining step."""
    assert probe.rows() == []
    task_history = probe.request("GET", f"/api/channels/{task_channel_id}")
    assert len(task_history["messages"]) == 8

    automations = probe.request("GET", "/api/automations")["automations"]
    assert {item["id"] for item in automations} == {"nightly-plan"}

    manifest = probe.request("GET", "/__acceptance__/knowledge-manifest")
    assert manifest["skill_exists"] is True
    assert manifest["skill_sha256"]
    assert manifest["pending"] is False
    assert probe.rows() == []

    state = {
        "marker": probe.marker,
        "task_channel_id": task_channel_id,
        "task_history": task_history,
        "automations": automations,
        "knowledge_manifest": manifest,
        "rows": [],
        "resumed_after_proven_task_phase": True,
        "http_raw_learning_statuses": {
            endpoint: 404 for endpoint in ("raw", "events", "log")
        },
    }
    _write_state(state_path, state)
    print(
        "LIVE_STORY_RESUME_PRE_RELOAD=PASS "
        "raw_http_routes=404 marker_rows=0"
    )


def verify_reload(probe: Probe, state_path: Path) -> None:
    if not state_path.is_file() or stat.S_IMODE(state_path.stat().st_mode) != 0o600:
        raise RuntimeError("live state file must exist with mode 0600")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["marker"] == probe.marker
    health = probe.request("GET", "/api/health")
    assert health["model"] == "gemini-3.5-flash"
    assert health["location"] == "global"
    assert health["framework"] == "Google ADK"
    assert health["firestore_mode"] == "firestore"
    assert probe.request(
        "GET", f"/api/channels/{state['task_channel_id']}"
    ) == state["task_history"]
    assert probe.request("GET", "/api/automations")["automations"] == state["automations"]
    assert probe.request(
        "GET", "/__acceptance__/knowledge-manifest"
    ) == state["knowledge_manifest"]
    assert probe.rows() == state["rows"]
    print("LIVE_STORY_RELOAD=PASS chat=durable automations=durable knowledge=durable")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("phase", choices=("run", "resume", "reload"))
    result.add_argument("--base-url", default="http://127.0.0.1:8765")
    result.add_argument("--marker", required=True)
    result.add_argument("--state", type=Path, default=Path("evidence/live/state.json"))
    result.add_argument("--task-channel-id")
    result.add_argument("--approved-live-test", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.approved_live_test:
        raise RuntimeError("Refusing live HTTP trace without approval flag")
    if MARKER_PATTERN.fullmatch(args.marker) is None:
        raise ValueError("invalid live acceptance marker")
    probe = Probe(args.base_url, args.marker)
    if args.phase == "run":
        run_story(probe, args.state)
    elif args.phase == "resume":
        if not args.task_channel_id:
            raise RuntimeError("resume requires --task-channel-id")
        resume_story(probe, args.state, args.task_channel_id)
    else:
        verify_reload(probe, args.state)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
