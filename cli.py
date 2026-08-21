"""Coroner from the command line.

    python cli.py case <trace.json>       autopsy one run, print the case file
    python cli.py graveyard [dir]         deterministic pass over every trace
    python cli.py autopsy-all [dir]       autopsy every trace, store the case files
    python cli.py fleet                   prescriptions across the stored case files
    python cli.py seed                    push local case files into the configured store
    python cli.py seed-traces [dir]       push raw traces in for the watcher to sweep
    python cli.py sweep [seconds]         autopsy every run that has gone quiet

Traces are redacted before they reach the model unless CORONER_REDACT=0.
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import sys
import time

from app import fleet, store, watch
from app.autopsy import perform_async
from app.findings import extract
from app.redact import redact
from app.traces import load

GRAVEYARD = os.path.expanduser("~/Documents/Agentonomy-Files/system/held-runs")
CONCURRENCY = int(os.environ.get("CORONER_CONCURRENCY", "6"))


def read(path: str):
    t = load(json.load(open(path)), run_id=os.path.basename(path)[:-5])
    if os.environ.get("CORONER_REDACT", "1") != "0":
        t = redact(t)
    return t, extract(t)


async def _autopsy_all(src: str) -> int:
    files = sorted(glob.glob(os.path.join(src, "*.json")))
    if not files:
        print(f"no traces in {src}")
        return 1
    sem = asyncio.Semaphore(CONCURRENCY)
    done = 0
    t0 = time.time()

    async def one(f: str):
        nonlocal done
        t, ev = read(f)
        async with sem:
            try:
                r = await perform_async(t, ev)
            except Exception as e:                      # one bad trace must not kill the batch
                print(f"  !! {t.run_id[:8]} {type(e).__name__}: {str(e)[:120]}")
                return
        store.save(r.as_dict())
        done += 1
        cert = r.certificate
        print(f"  {done:>2}/{len(files)} {t.run_id[:8]} {cert.get('cause','?'):<22} "
              f"{cert.get('confidence',0):.2f}  {t.title[:40]}")

    await asyncio.gather(*(one(f) for f in files))
    print(f"\n{done}/{len(files)} case files stored in {time.time()-t0:.0f}s")
    return 0 if done else 1


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]

    if cmd == "graveyard":
        src = rest[0] if rest else GRAVEYARD
        for f in sorted(glob.glob(os.path.join(src, "*.json"))):
            t, ev = read(f)
            print(f"{ev.prior_cause:<22} {t.progress:>5.0%}  {t.title[:56]}")
        return 0

    if cmd == "case":
        t, ev = read(rest[0])
        r = asyncio.run(perform_async(t, ev))
        store.save(r.as_dict())
        print(json.dumps(r.as_dict(), indent=2))
        return 0

    if cmd == "autopsy-all":
        return asyncio.run(_autopsy_all(rest[0] if rest else GRAVEYARD))

    if cmd == "seed":
        # Copy the local case files into whatever store is configured. Used once
        # to put the demo corpus in Firestore for the hosted deployment.
        src = os.environ.get("CORONER_LOCAL_STORE", "data/cases")
        n = 0
        for f in sorted(glob.glob(os.path.join(src, "*.json"))):
            store.save(json.load(open(f)))
            n += 1
        print(f"seeded {n} case files into "
              f"{'firestore' if os.environ.get('CORONER_STORE') == 'firestore' else src}")
        return 0

    if cmd == "seed-traces":
        src = rest[0] if rest else "data/demo-traces"
        n = 0
        for f in sorted(glob.glob(os.path.join(src, "*.json"))):
            raw = json.load(open(f))
            store.put_trace(raw.get("runId") or os.path.basename(f)[:-5], raw)
            n += 1
        print(f"seeded {n} traces for the watcher")
        return 0

    if cmd == "sweep":
        r = asyncio.run(watch.sweep(after=int(rest[0]) if rest else watch.SILENT_AFTER))
        print(json.dumps(r.as_dict(), indent=2))
        return 0

    if cmd == "fleet":
        cases = store.all_cases()
        if not cases:
            print("no case files stored — run autopsy-all first")
            return 1
        print(json.dumps(fleet.prescribe(cases), indent=2))
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
