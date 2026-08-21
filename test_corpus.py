"""Self-check: the taxonomy has to survive contact with the real corpus.

Run: python3 test_corpus.py [path-to-held-runs]
"""
import json, sys, glob, os, collections
from app.traces import load
from app.findings import extract, CAUSES

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/Documents/Agentonomy-Files/system/held-runs")


def main() -> int:
    files = sorted(glob.glob(os.path.join(SRC, "*.json")))
    assert files, f"no traces found in {SRC}"

    dist = collections.Counter()
    silent = 0
    stalled_progress = []
    progress_all = []

    for f in files:
        raw = json.load(open(f))
        t = load(raw, run_id=os.path.basename(f)[:-5])
        ev = extract(t)

        assert t.run_id, f"{f}: no run id"
        assert ev.prior_cause in CAUSES, f"{f}: unknown cause {ev.prior_cause}"
        assert 0.0 <= ev.progress <= 1.0, f"{f}: progress out of range"
        assert ev.signals, f"{f}: extracted no signals at all"

        dist[ev.prior_cause] += 1
        progress_all.append(t.progress)
        if ev.silent:
            silent += 1
        if ev.prior_cause != "USER_ABORT":
            stalled_progress.append(ev.progress)

    n = len(files)
    undetermined = dist["UNDETERMINED"]
    print(f"corpus: {n} traces\n")
    for cause, k in dist.most_common():
        print(f"  {k:>3}  {cause:<22} {CAUSES[cause][0]}")

    avg = sum(stalled_progress) / len(stalled_progress) if stalled_progress else 0
    print(f"\n  silent stops (never reported a failure): {silent}/{n} = {silent/n:.0%}")
    print(f"  mean progress of runs that died unintentionally: {avg:.1%}")

    # The taxonomy is only worth shipping if it explains most of the corpus.
    assert undetermined / n <= 0.15, (
        f"taxonomy explains too little: {undetermined}/{n} undetermined")
    print(f"\nOK — {n-undetermined}/{n} traces attributed "
          f"({undetermined} undetermined, under the 15% budget)")

    # The published corpus is only honest if it is the same corpus with the
    # names changed: identical structure, none of the content.
    twin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "demo-traces")
    if os.path.isdir(twin) and os.path.abspath(twin) != os.path.abspath(SRC):
        tdist, tprog = collections.Counter(), []
        for f in sorted(glob.glob(os.path.join(twin, "*.json"))):
            t = load(json.load(open(f)), run_id=os.path.basename(f)[:-5])
            tdist[extract(t).prior_cause] += 1
            tprog.append(round(t.progress, 4))
        if tdist:
            assert tdist == dist, f"published corpus drifted: {tdist} != {dist}"
            assert tprog == [round(p, 4) for p in progress_all], "published corpus progress drifted"
            print(f"     published twin in data/demo-traces matches on structure "
                  f"({sum(tdist.values())} traces)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
