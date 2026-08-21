"""Strip identifying content out of a trace before anything leaves the machine.

A dead run's trace is full of the work it was doing: file paths, internal
hostnames, credentials the worker echoed back, whatever the human asked for.
An autopsy needs the *shape* of the run, not its contents, so redaction is
cheap here in a way it usually is not.

Placeholders are typed and stable — <path>, <url>, <email> — so a model can
still see that a step referenced a file, and that two steps referenced the
same one, without seeing which file.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import replace

from .traces import Trace

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
    ("url", re.compile(r"\bhttps?://[^\s'\"<>)\]]+")),
    ("token", re.compile(r"\b(?:sk|pk|ghp|gho|xox[baprs])[-_][A-Za-z0-9_-]{16,}\b")),
    ("key", re.compile(r"\b[A-Fa-f0-9]{32,}\b")),
    ("path", re.compile(r"(?:/[\w.\-]+){2,}/?")),
    ("ip", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")),
]


def _tag(kind: str, value: str) -> str:
    """Same value -> same placeholder, so cross-references survive redaction."""
    return f"<{kind}:{hashlib.sha256(value.encode()).hexdigest()[:6]}>"


def scrub(text: str) -> str:
    if not text:
        return text
    for kind, pat in _PATTERNS:
        text = pat.sub(lambda m: _tag(kind, m.group(0)), text)
    return text


def redact(t: Trace) -> Trace:
    """A trace with the same structure and none of the content."""
    return replace(
        t,
        title=scrub(t.title),
        request=scrub(t.request),
        stop_reason=scrub(t.stop_reason),
        steps=[
            replace(
                s,
                title=scrub(s.title),
                instruction=scrub(s.instruction),
                acceptance=scrub(s.acceptance),
                result=scrub(s.result),
            )
            for s in t.steps
        ],
    )


def demo():
    """python -m app.redact — the check that matters is that nothing leaks."""
    dirty = (
        "Read /Users/ada/Documents/secret-project/plan.md then POST to "
        "http://localhost:3006/api/chats with key deadbeefcafebabe0123456789abcdef "
        "and mail ada@example.com from 10.0.0.4"
    )
    clean = scrub(dirty)
    for leak in ("ada", "secret-project", "localhost", "deadbeef", "example.com", "10.0.0.4"):
        assert leak not in clean, f"leaked {leak!r}: {clean}"
    # Same input twice must give the same placeholder, or cross-references break.
    assert scrub("/a/b/c") == scrub("/a/b/c")
    assert scrub("/a/b/c") != scrub("/a/b/d")
    print(clean)
    print("OK — nothing leaked, placeholders stable")


if __name__ == "__main__":
    demo()
