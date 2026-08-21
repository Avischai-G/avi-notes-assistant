"""Canonical trace format + adapters.

A trace is whatever an orchestrator left behind when a run stopped. Every
orchestrator writes something different, so everything upstream of this module
is vendor-specific and everything downstream is not.
"""
from __future__ import annotations
import json
import math
from dataclasses import dataclass, field, asdict
from typing import Any


# Parsing limits are deliberately well above the real corpus (33 steps and a
# 12,126-character longest field) while still bounding work on hostile input.
MAX_STEPS = 500
MAX_TEXT_CHARS = 16_384
MAX_ID_CHARS = 256
MAX_JSON_DEPTH = 20
MAX_JSON_NODES = 20_000
MAX_ATTEMPTS = 10_000

STEP_STATUSES = frozenset({"done", "doing", "todo", "blocked", "user", "unknown"})
RUN_STATUSES = frozenset({"held", "running", "done", "failed", "unknown"})


@dataclass
class Step:
    id: str
    title: str
    agent: str = ""
    status: str = ""          # done | doing | todo | blocked | user | unknown
    depends_on: list[str] = field(default_factory=list)
    difficulty: str = ""
    instruction: str = ""     # what the worker was told to do
    acceptance: str = ""      # how the orchestrator would have judged it
    result: str = ""          # what the worker reported back, if anything
    attempts: int = 0         # retries are evidence: a step tried 3 times died differently


@dataclass
class Trace:
    run_id: str
    title: str
    final_state: str          # held | running | done | failed
    stop_reason: str          # verbatim, whatever the orchestrator said
    request: str              # what the human originally asked for
    steps: list[Step] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    worker_failures: int = 0
    source: str = "unknown"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    # --- derived signals the analyst agents reason over -------------------
    @property
    def counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for s in self.steps:
            c[s.status or "unknown"] = c.get(s.status or "unknown", 0) + 1
        return c

    @property
    def progress(self) -> float:
        """Fraction of planned steps actually banked. The number that matters."""
        if not self.steps:
            return 0.0
        return len([s for s in self.steps if s.status == "done"]) / len(self.steps)

    @property
    def retries(self) -> int:
        return sum(max(0, s.attempts - 1) for s in self.steps)

    @property
    def is_silent(self) -> bool:
        """Stopped without ever reporting a failure. The dangerous kind."""
        return self.final_state in ("held", "running") and self.worker_failures == 0


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def _check_text(value: str, path: str, maximum: int = MAX_TEXT_CHARS) -> None:
    if len(value) > maximum:
        raise ValueError(f"{path} exceeds the maximum of {maximum} characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{path} must contain valid Unicode") from exc


def _validate_json(value: Any) -> None:
    """Bound arbitrary direct callers too, not only the HTTP request body."""
    stack = [(value, 1, "trace", False)]
    active: set[int] = set()
    scheduled = 1

    while stack:
        item, depth, path, leaving = stack.pop()
        if leaving:
            active.remove(id(item))
            continue

        if isinstance(item, (dict, list)):
            if depth > MAX_JSON_DEPTH:
                raise ValueError(
                    f"trace nesting exceeds the maximum of {MAX_JSON_DEPTH} levels at {path}"
                )
            marker = id(item)
            if marker in active:
                raise ValueError(f"trace contains a circular container at {path}")
            active.add(marker)
            stack.append((item, depth, path, True))

            scheduled += len(item)
            if scheduled > MAX_JSON_NODES:
                raise ValueError(
                    f"trace exceeds the maximum of {MAX_JSON_NODES} JSON values"
                )

            if isinstance(item, dict):
                for key, child in reversed(list(item.items())):
                    if not isinstance(key, str):
                        raise ValueError(f"{path} has a non-string object key")
                    _check_text(key, f"object key in {path}")
                    child_path = f"{path}.{key}" if len(key) <= 80 else f"{path}.[long key]"
                    stack.append((child, depth + 1, child_path, False))
            else:
                for index in range(len(item) - 1, -1, -1):
                    stack.append((item[index], depth + 1, f"{path}[{index}]", False))
        elif isinstance(item, str):
            _check_text(item, path)
        elif item is None or isinstance(item, (bool, int)):
            continue
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError(f"{path} must be a finite JSON number")
        else:
            raise ValueError(f"{path} contains non-JSON value of type {_kind(item)}")


def _text(raw: dict[str, Any], key: str, path: str, *, strip: bool = False) -> str:
    value = raw.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{path}.{key} must be a string or null, got {_kind(value)}")
    return value.strip() if strip else value


def _identifier(value: Any, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{path} must be a string or integer, got {_kind(value)}")
    out = str(value).strip()
    if not out:
        raise ValueError(f"{path} must not be empty")
    _check_text(out, path, MAX_ID_CHARS)
    return out


def _references(raw: dict[str, Any], key: str, path: str) -> list[str]:
    value = raw.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{path}.{key} must be an array or null, got {_kind(value)}")
    if len(value) > MAX_STEPS:
        raise ValueError(f"{path}.{key} exceeds the maximum of {MAX_STEPS} entries")
    return [_identifier(item, f"{path}.{key}[{i}]") for i, item in enumerate(value)]


def _integer(raw: dict[str, Any], key: str, path: str) -> int:
    value = raw.get(key)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path}.{key} must be a non-negative integer, got {_kind(value)}")
    if not 0 <= value <= MAX_ATTEMPTS:
        raise ValueError(f"{path}.{key} must be between 0 and {MAX_ATTEMPTS}")
    return value


def _status(value: Any, path: str, allowed: frozenset[str]) -> str:
    if value is None or value == "":
        return "unknown"
    if not isinstance(value, str):
        raise ValueError(f"{path} must be a string or null, got {_kind(value)}")
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{path} has unknown value {value!r}; expected one of: {choices}")
    return value


def _step_id(raw: dict[str, Any], index: int) -> str:
    for key in ("taskId", "step"):
        if raw.get(key) not in (None, ""):
            return _identifier(raw[key], f"trace.steps[{index}].{key}")
    return str(index)


def _result(raw: dict[str, Any], path: str) -> str:
    value = raw.get("result")
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if not value:  # Preserve the adapter's existing treatment of 0/false/empty.
        return ""
    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    _check_text(rendered, f"{path}.result")
    return rendered


def from_agentonomy(raw: dict[str, Any], run_id: str = "") -> Trace:
    """Adapter for Agentonomy held-run JSON."""
    if not isinstance(raw, dict):
        raise ValueError(f"trace body must be a JSON object, got {_kind(raw)}")
    _validate_json(raw)

    if "steps" not in raw:
        raise ValueError("trace is missing required field 'steps'")
    raw_steps = raw["steps"]
    if not isinstance(raw_steps, list):
        raise ValueError(f"trace.steps must be an array, got {_kind(raw_steps)}")
    if len(raw_steps) > MAX_STEPS:
        raise ValueError(f"trace.steps exceeds the maximum of {MAX_STEPS} steps")

    raw_run_id = raw.get("runId")
    if raw_run_id in (None, ""):
        if not run_id:
            raise ValueError("trace.runId is required and must be a non-empty string")
        actual_run_id = _identifier(run_id, "run_id fallback")
    else:
        if not isinstance(raw_run_id, str):
            raise ValueError(f"trace.runId must be a string, got {_kind(raw_run_id)}")
        actual_run_id = _identifier(raw_run_id, "trace.runId")

    steps: list[Step] = []
    for i, raw_step in enumerate(raw_steps):
        path = f"trace.steps[{i}]"
        if not isinstance(raw_step, dict):
            raise ValueError(f"{path} must be an object, got {_kind(raw_step)}")
        steps.append(Step(
            id=_step_id(raw_step, i),
            title=_text(raw_step, "title", path, strip=True),
            agent=_text(raw_step, "agent", path),
            status=_status(raw_step.get("status"), f"{path}.status", STEP_STATUSES),
            depends_on=_references(raw_step, "dependsOn", path),
            difficulty=_text(raw_step, "difficulty", path),
            instruction=_text(raw_step, "instruction", path, strip=True),
            acceptance=_text(raw_step, "acceptance", path, strip=True),
            result=_result(raw_step, path),
            attempts=_integer(raw_step, "attempts", path),
        ))

    title = _text(raw, "title", "trace", strip=True)
    return Trace(
        run_id=actual_run_id,
        title=title or "(untitled run)",
        final_state=_status(raw.get("status"), "trace.status", RUN_STATUSES),
        stop_reason=_text(raw, "reason", "trace", strip=True),
        request=_text(raw, "originalRequest", "trace", strip=True),
        steps=steps,
        completed=_references(raw, "completedSteps", "trace"),
        worker_failures=_integer(raw, "cliFailures", "trace"),
        source="agentonomy",
    )


ADAPTERS = {"agentonomy": from_agentonomy}


def detect(raw: dict[str, Any]) -> str:
    if not isinstance(raw, dict):
        raise ValueError(f"trace body must be a JSON object, got {_kind(raw)}")
    if "steps" not in raw:
        raise ValueError("trace is missing required field 'steps'")
    if not isinstance(raw["steps"], list):
        raise ValueError(f"trace.steps must be an array, got {_kind(raw['steps'])}")
    return "agentonomy"


def load(raw: Any, run_id: str = "") -> Trace:
    return ADAPTERS[detect(raw)](raw, run_id)
