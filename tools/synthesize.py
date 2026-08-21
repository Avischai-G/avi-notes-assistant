"""Build a publishable corpus with the same skeleton as a private one.

The 39 traces Coroner was designed against are real runs from a production
orchestrator, and they are full of somebody's actual work. They cannot ship.
But the *shape* of a dead run — its statuses, its dependency graph, how many
times a step retried, what the orchestrator recorded as the reason — is what
the diagnosis is made of, and none of that is private.

So: keep every structural field byte-for-byte, and have Gemini re-tell the
project content as an unrelated fictional project. The deterministic layer
produces identical evidence for a synthetic twin, which is the point — the
demo corpus is not a mock-up, it is the same corpus with the names changed.

    python tools/synthesize.py [src-dir] [out-dir]
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app  # noqa: F401  (loads .env)
from google import genai
from google.genai import types
from pydantic import BaseModel

MODEL = os.environ.get("CORONER_SYNTH_MODEL", "gemini-3.5-flash")

# Structural fields are copied verbatim. Everything else is regenerated.
KEEP_RUN = {"version", "runId", "chatId", "status", "reason", "boardId", "tier",
            "completedSteps", "resumeMessages", "cliFailures", "legacy", "updatedAt"}
KEEP_STEP = {"step", "agent", "difficulty", "dependsOn", "taskId", "status", "attempts"}

DOMAINS = [
    "a bicycle courier dispatch tool", "a community seed library catalogue",
    "a tide-and-swell forecast page for surfers", "a museum audio-guide builder",
    "a rehearsal scheduler for a brass band", "an allotment watering roster",
    "a lighthouse maintenance log", "a secondhand bookshop stock system",
    "a climbing-gym route-setting tracker", "a beekeeping hive inspection app",
    "a village hall booking system", "a model-railway timetable simulator",
    "a food-bank stock rotation dashboard", "a lighthouse keeper's weather journal",
]


class Step(BaseModel):
    title: str
    instruction: str
    acceptance: str
    result: str


class Fiction(BaseModel):
    title: str
    original_request: str
    steps: list[Step]


PROMPT = """You are rewriting the *content* of a software project's task board so
it can be published, while leaving its structure untouched.

The real project is confidential. Replace it with: {domain}.

Write {n} steps, in order. For each one you are given its status and how many
attempts it took; your text must be consistent with that:

{skeleton}

Rules:
- 'result' must be non-empty ONLY for the steps marked below as having one, and
  must read like a worker agent reporting back — including reporting failure or
  being stuck where the status says so.
- A step with status 'done' reads as completed work. 'todo' has no result.
  'blocked' explains what stood in the way. 'user' is a question put to a human.
- Never mention the real domain, real people, file paths, URLs, or credentials.
- Keep the register dry and technical. This is a work log, not marketing.
"""


def skeleton(raw: dict) -> str:
    out = []
    for i, s in enumerate(raw.get("steps") or []):
        out.append(
            f"  {i+1}. status={s.get('status','?')} attempts={s.get('attempts') or 1} "
            f"agent={s.get('agent','?')} difficulty={s.get('difficulty','?')} "
            f"{'HAS a result' if s.get('result') else 'no result'}")
    return "\n".join(out) or "  (no steps were ever planned)"


async def one(client, raw: dict, i: int) -> dict:
    steps = raw.get("steps") or []
    out = {k: v for k, v in raw.items() if k in KEEP_RUN}

    if not steps:
        out.update(title="Recovered work", originalRequest="", latestMessage="", steps=[])
        return out

    r = await client.aio.models.generate_content(
        model=MODEL,
        contents=PROMPT.format(domain=DOMAINS[i % len(DOMAINS)],
                               n=len(steps), skeleton=skeleton(raw)),
        config=types.GenerateContentConfig(
            temperature=1.0, response_mime_type="application/json", response_schema=Fiction),
    )
    f = Fiction.model_validate_json(r.text)

    new_steps = []
    for s, fake in zip(steps, f.steps + [Step(title="", instruction="", acceptance="", result="")] * len(steps)):
        ns = {k: v for k, v in s.items() if k in KEEP_STEP}
        ns["title"] = fake.title
        ns["instruction"] = fake.instruction
        ns["acceptance"] = fake.acceptance
        if s.get("result"):
            ns["result"] = fake.result
        new_steps.append(ns)

    # Titles like "Recovered work" are orchestrator-generated, not user content.
    out["title"] = raw.get("title") if raw.get("title") == "Recovered work" else f.title
    out["originalRequest"] = f.original_request
    out["latestMessage"] = f.original_request
    out["steps"] = new_steps
    return out


async def main(src: str, dst: str) -> int:
    files = sorted(Path(src).glob("*.json"))
    if not files:
        print(f"no traces in {src}")
        return 1
    Path(dst).mkdir(parents=True, exist_ok=True)
    client = genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"],
                          location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"))
    sem = asyncio.Semaphore(6)

    async def work(p: Path, i: int):
        raw = json.loads(p.read_text())
        async with sem:
            try:
                fake = await one(client, raw, i)
            except Exception as e:
                print(f"  !! {p.name[:8]} {type(e).__name__}: {str(e)[:110]}")
                return
        (Path(dst) / p.name).write_text(json.dumps(fake, indent=2))
        print(f"  {p.name[:8]}  {len(fake.get('steps') or [])} steps  {fake.get('title','')[:52]}")

    await asyncio.gather(*(work(p, i) for i, p in enumerate(files)))
    n = len(list(Path(dst).glob("*.json")))
    print(f"\n{n}/{len(files)} synthetic traces in {dst}")
    return 0 if n == len(files) else 1


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        "~/Documents/Agentonomy-Files/system/held-runs")
    dst = sys.argv[2] if len(sys.argv) > 2 else "data/demo-traces"
    raise SystemExit(asyncio.run(main(src, dst)))
