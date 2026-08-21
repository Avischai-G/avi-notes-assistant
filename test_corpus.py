"""Self-check: the taxonomy has to survive contact with a frozen corpus.

Run: python3 test_corpus.py [path-to-held-runs]
"""
import json, sys, glob, os, collections
from app.traces import load
from app.findings import extract, CAUSES

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "demo-traces")


def main() -> int:
    files = sorted(glob.glob(os.path.join(SRC, "*.json")))
    if not files:
        print(f"ERROR — zero traces selected from {SRC}", file=sys.stderr)
        return 1

    dist = collections.Counter()
    silent = 0
    stalled_progress = []
    for f in files:
        raw = json.load(open(f))
        t = load(raw, run_id=os.path.basename(f)[:-5])
        ev = extract(t)

        assert t.run_id, f"{f}: no run id"
        assert ev.prior_cause in CAUSES, f"{f}: unknown cause {ev.prior_cause}"
        assert 0.0 <= ev.progress <= 1.0, f"{f}: progress out of range"
        assert ev.signals, f"{f}: extracted no signals at all"

        dist[ev.prior_cause] += 1
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
        # Compare trace by trace over what the two corpora share. The private
        # corpus keeps growing; that is not drift, but a twin whose structure
        # has diverged from its original is.
        checked = 0
        for f in sorted(glob.glob(os.path.join(twin, "*.json"))):
            original = os.path.join(SRC, os.path.basename(f))
            if not os.path.exists(original):
                continue
            original_raw = json.load(open(original))
            a = load(original_raw, run_id="x")
            b = load(json.load(open(f)), run_id="x")
            name = os.path.basename(f)[:8]
            assert extract(a).prior_cause == extract(b).prior_cause, f"{name}: cause drifted"
            assert round(a.progress, 6) == round(b.progress, 6), f"{name}: progress drifted"
            assert [s.status for s in a.steps] == [s.status for s in b.steps], f"{name}: statuses drifted"
            assert [s.depends_on for s in a.steps] == [s.depends_on for s in b.steps], f"{name}: graph drifted"
            assert [s.attempts for s in a.steps] == [s.attempts for s in b.steps], f"{name}: retries drifted"
            checked += 1
        assert checked, "a published twin exists but shares no traces with the private corpus"
        print(f"     published twin matches the original on cause, progress, statuses, "
              f"dependency graph and retries ({checked} traces)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
