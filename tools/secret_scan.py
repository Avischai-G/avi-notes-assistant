#!/usr/bin/env python3
"""Scan the final worktree and every reachable git revision without leaking hits."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".npm-cache",
    ".pytest_cache",
    ".python",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "node_modules",
}


def _notion_values() -> list[tuple[str, bytes]]:
    path = Path.home() / ".config" / "agentonomy" / "notion.env"
    if not path.is_file():
        return []
    values: list[tuple[str, bytes]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() in {"NOTION_TOKEN", "NOTION_TASKS_DATABASE_ID"}:
            clean = value.strip().strip('"').strip("'")
            if clean:
                values.append((name.strip(), clean.encode()))
    return values


def _google_values() -> list[tuple[str, bytes]]:
    candidates = [
        Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    ]
    configured = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if configured:
        candidates.append(Path(configured).expanduser())
    sensitive_keys = {
        "private_key",
        "private_key_id",
        "client_email",
        "client_id",
        "client_secret",
        "refresh_token",
    }
    values: list[tuple[str, bytes]] = []
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        for key in sensitive_keys:
            value = data.get(key)
            if isinstance(value, str) and len(value) >= 8:
                values.append((f"google:{key}", value.encode()))
    return values


def _worktree_files() -> list[Path]:
    files: list[Path] = []
    for directory, names, filenames in os.walk(ROOT):
        names[:] = [name for name in names if name not in EXCLUDED_PARTS]
        base = Path(directory)
        for filename in filenames:
            path = base / filename
            if not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts):
                files.append(path)
    return sorted(files)


def _generic_patterns() -> list[tuple[str, re.Pattern[bytes]]]:
    token_prefix = rb"(?:ntn" + rb"_|secret" + rb"_)"
    return [
        (
            "notion-token-shape",
            re.compile(rb"\b" + token_prefix + rb"[A-Za-z0-9._-]{12,}"),
        ),
        (
            "private-key-block",
            re.compile(
                rb"-----BEGIN "
                + rb"PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{64,}-----END "
                + rb"PRIVATE KEY-----"
            ),
        ),
        (
            "oauth-refresh-token",
            re.compile(rb'"refresh_' + rb'token"\s*:\s*"[^"\r\n]{8,}"'),
        ),
        (
            "oauth-client-secret",
            re.compile(rb'"client_' + rb'secret"\s*:\s*"[^"\r\n]{8,}"'),
        ),
    ]


def _history_bytes() -> bytes:
    result = subprocess.run(
        ["git", "log", "--all", "-p", "--no-ext-diff", "--binary", "--format=fuller"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("git history extraction failed")
    return result.stdout


def main() -> int:
    exact = _notion_values() + _google_values()
    patterns = _generic_patterns()
    worktree_hits: list[tuple[str, str]] = []
    files = _worktree_files()
    for path in files:
        try:
            content = path.read_bytes()
        except OSError:
            continue
        relative = path.relative_to(ROOT).as_posix()
        for label, value in exact:
            if value in content:
                worktree_hits.append((relative, f"exact:{label}"))
        for label, pattern in patterns:
            if pattern.search(content):
                worktree_hits.append((relative, label))

    history = _history_bytes()
    history_hits: list[str] = []
    for label, value in exact:
        if value in history:
            history_hits.append(f"exact:{label}")
    for label, pattern in patterns:
        if pattern.search(history):
            history_hits.append(label)

    if worktree_hits or history_hits:
        print("SECRET_SCAN=FAIL")
        for path, label in sorted(set(worktree_hits)):
            print(f"worktree_hit={path} kind={label}")
        for label in sorted(set(history_hits)):
            print(f"history_hit kind={label}")
        return 1

    print(
        "SECRET_SCAN=PASS "
        f"worktree_files={len(files)} reachable_history_bytes={len(history)} "
        f"exact_sensitive_values={len(exact)} generic_patterns={len(patterns)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
