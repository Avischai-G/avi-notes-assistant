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
    ("private-key", re.compile(
        r"-----BEGIN (?P<private_kind>[A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?)-----"
        r"[\s\S]*?-----END (?P=private_kind)-----", re.I)),
    ("database", re.compile(
        r"\b(?:jdbc:)?(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|"
        r"redis|rediss|amqps?|mssql|sqlserver)://[^\s'\"<>)\]]+", re.I)),
    ("database", re.compile(
        r"\b(?:Server|Data Source)=[^\r\n]+?(?:Password|Pwd)=[^;\r\n]+"
        r"(?:;[^\r\n]*)?", re.I)),
    ("bearer", re.compile(r"\bBearer[ \t]+[A-Za-z0-9._~+/=-]{8,}", re.I)),
    ("jwt", re.compile(
        r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA|AIDA|AROA|AIPA|ANPA|ANVA|ASCA)"
                           r"[A-Z0-9]{16}\b")),
    ("aws-secret", re.compile(
        r"\baws_secret_access_key\s*[:=]\s*[A-Za-z0-9/+=]{40}\b", re.I)),
    ("url", re.compile(r"\bhttps?://[^\s'\"<>)\]]+")),
    ("url", re.compile(
        r"(?<![@\w.-])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}"
        r"(?::\d{1,5})?/[^\s'\"<>)\]]*")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
    ("path", re.compile(
        r"\\\\[^\\\s\"'<>|]+\\[^\\\s\"'<>|]+"
        r"(?:\\[^\\\s\"'<>|]+)*\\?")),
    ("path", re.compile(
        r"\b[A-Za-z]:\\(?:[^\\\s\"'<>|]+\\)*[^\\\s\"'<>|]+\\?")),
    ("token", re.compile(r"\b(?:sk|pk|ghp|gho|xox[baprs])[-_][A-Za-z0-9_-]{16,}\b")),
    ("key", re.compile(r"\b[A-Fa-f0-9]{32,}\b")),
    ("path", re.compile(r"(?:/[\w.\-]+){2,}/?")),
    ("ip", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")),
]


def _tag(kind: str, value: str) -> str:
    """Same value -> same placeholder, so cross-references survive redaction."""
    digest = hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()[:6]
    return f"<{kind}:{digest}>"


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

    jwt = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
           "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
           "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")
    cases = [
        ("path", r"C:\Users\Ada\Documents\secret.txt", ("Ada", "secret.txt")),
        ("path", r"\\fileserver\finance\budget.xlsx", ("fileserver", "budget.xlsx")),
        ("url", "api.internal.corp/v1/users?q=secret", ("internal.corp", "q=secret")),
        ("jwt", jwt, ("eyJhbGci", "SflKxw")),
        ("private-key", "-----BEGIN PRIVATE KEY-----\nabcDEF0123+/=\n"
                        "-----END PRIVATE KEY-----", ("BEGIN PRIVATE", "abcDEF")),
        ("database", "postgresql://alice:s3cret@db.internal.corp:5432/coroner",
                     ("alice", "s3cret", "db.internal.corp")),
        ("aws-key", "AKIAIOSFODNN7EXAMPLE", ("AKIAIOSF", "EXAMPLE")),
        ("aws-secret", "aws_secret_access_key="
                       "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                       ("wJalrXU", "EXAMPLEKEY")),
        ("bearer", "Authorization: Bearer mF_9.B5f-4.1JqM",
                   ("mF_9", "1JqM")),
    ]
    for kind, dirty_value, leaks in cases:
        scrubbed = scrub(dirty_value)
        assert f"<{kind}:" in scrubbed, f"did not redact {kind}: {scrubbed}"
        for leak in leaks:
            assert leak not in scrubbed, f"{kind} leaked {leak!r}: {scrubbed}"

    # Same input twice must give the same placeholder, or cross-references break.
    assert scrub("/a/b/c") == scrub("/a/b/c")
    assert scrub("/a/b/c") != scrub("/a/b/d")
    print(clean)
    print("OK — nothing leaked, placeholders stable")


if __name__ == "__main__":
    demo()
