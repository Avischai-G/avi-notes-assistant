"""The published corpus must carry none of the private one.

This is the check standing between a private graveyard and a public demo.

Shared vocabulary is not a leak — two software work logs will both say
"documentation" and "timestamp", and counting those only produces noise. Nor
is an accented character: the fiction invents European names of its own. What
constitutes a leak is *verbatim carry-over*: a phrase somebody actually typed
surviving into the twin. So the test looks for shared word shingles across the
free-text fields, plus the handful of strings that must never appear at all.

    python test_published.py [private-dir] [published-dir]
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

PRIVATE = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/Documents/Agentonomy-Files/system/held-runs")
PUBLISHED = sys.argv[2] if len(sys.argv) > 2 else "data/demo-traces"

# Never present, under any phrasing.
BANNED = ("agentonomy", "avischaigrau", "avischai", "localhost", "gen-lang-client")

SHINGLE = 6          # six consecutive words in common is nobody's coincidence
WORD = re.compile(r"\w+")

# The orchestrator's own stop-reason boilerplate is preserved on purpose — the
# rules classify on it, so it is signal, not content. Only the part a human or
# an agent actually composed after it counts as free text.
WAITING = re.compile(r"^waiting for the user:\s*", re.I)


def free_reason(reason: str) -> str:
    m = WAITING.match(reason or "")
    return reason[m.end():] if m else ""


# Free text — the fields a human or a worker agent wrote into.
def texts(raw: dict):
    yield raw.get("title") or ""
    yield raw.get("originalRequest") or ""
    yield raw.get("latestMessage") or ""
    yield free_reason(raw.get("reason") or "")
    for m in raw.get("resumeMessages") or []:
        yield (m or {}).get("content") or ""
    for s in raw.get("steps") or []:
        for k in ("title", "instruction", "acceptance", "result"):
            v = s.get(k)
            yield v if isinstance(v, str) else ""


def shingles(raw: dict) -> set[tuple[str, ...]]:
    out = set()
    for t in texts(raw):
        w = [x.lower() for x in WORD.findall(t)]
        out.update(tuple(w[i:i + SHINGLE]) for i in range(len(w) - SHINGLE + 1))
    return out


def load_all(path: str) -> list[dict]:
    return [json.loads(open(f, encoding="utf-8").read())
            for f in sorted(glob.glob(os.path.join(path, "*.json")))]


def main() -> int:
    pub_files = sorted(glob.glob(os.path.join(PUBLISHED, "*.json")))
    assert pub_files, f"nothing published in {PUBLISHED}"
    private, published = load_all(PRIVATE), load_all(PUBLISHED)

    # 1. Hard bans.
    for f in pub_files:
        blob = open(f, encoding="utf-8").read().lower()
        for banned in BANNED:
            assert banned not in blob, f"{banned!r} present in {os.path.basename(f)}"

    # 2. Verbatim carry-over — the thing that actually constitutes a leak.
    priv_sh: set[tuple[str, ...]] = set()
    for raw in private:
        priv_sh |= shingles(raw)

    leaked = []
    for f, raw in zip(pub_files, published):
        for s in shingles(raw) & priv_sh:
            leaked.append((os.path.basename(f)[:8], " ".join(s)))

    if leaked:
        print(f"VERBATIM CARRY-OVER — {len(leaked)} shared {SHINGLE}-word phrases:")
        for f, s in leaked[:15]:
            print(f"  {f}  …{s}…")
    assert not leaked, f"{len(leaked)} phrases survived from the private corpus"

    print(f"private traces: {len(private)}   published: {len(published)}")
    print(f"distinct {SHINGLE}-word phrases in private corpus: {len(priv_sh)}")
    print("OK — no banned strings and no phrasing carried over from the private corpus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
