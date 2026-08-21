"""Self-check: the stream reports the pipeline the way a viewer has to see it.

    python test_stream.py

No model calls — a fake stage runner replays what the six agents emit, so what
is under test is the ordering the interface is built against: every stage
starts before it finishes, and the three investigators are all reported running
at once rather than one after another.
"""
from __future__ import annotations

import asyncio

from app.autopsy import GROUP, OUTPUT_KEY, WAVES, Report, watch_autopsy

CASE = Report(run_id="fake", title="a run that died", prior_cause="UNDETERMINED",
              evidence={}, hypotheses=[], verdicts={}, certificate={"cause": "X"},
              resume_plan={}).as_dict()


def _fake(explode_at: str | None = None):
    async def run(t, ev, on_event=None):
        for wave in WAVES:
            for stage in reversed(wave):        # out of order inside the wave
                if stage == explode_at:
                    raise RuntimeError("the model hung up")
                await on_event({"agent": stage, "final": False, "produced": {}})
                await on_event({"agent": stage, "final": True,
                                "produced": {OUTPUT_KEY[stage]: {"from": stage}}})
        return Report(**{k: CASE[k] for k in CASE})
    return run


async def collect(run):
    return [e async for e in watch_autopsy(None, None, run=run)]


def main() -> int:
    events = asyncio.run(collect(_fake()))
    names = [n for n, _ in events]
    assert names[-1] == "done", names[-1]
    assert set(names[:-1]) == {"stage"}, "nothing but stage events until the end"
    assert events[-1][1]["case"] == CASE, "the done event carries the whole case"

    stages = [d for n, d in events if n == "stage"]
    starts = [d for d in stages if d["state"] == "start"]
    dones = [d for d in stages if d["state"] == "done"]
    order = [s for wave in WAVES for s in wave]
    assert len(starts) == len(dones) == 6, (len(starts), len(dones))
    assert sorted(d["stage"] for d in dones) == sorted(order), "every stage reports back"
    # Waves finish in pipeline order; within a wave, whoever finishes first does.
    wave_of = {s: i for i, wave in enumerate(WAVES) for s in wave}
    seq = [wave_of[d["stage"]] for d in dones]
    assert seq == sorted(seq), f"waves finished out of order: {seq}"

    for stage in order:
        i = next(k for k, d in enumerate(stages) if d["stage"] == stage and d["state"] == "start")
        j = next(k for k, d in enumerate(stages) if d["stage"] == stage and d["state"] == "done")
        assert i < j, f"{stage} reported done before it reported start"

    # The whole reason the stream exists: three things visibly running at once.
    lens = WAVES[1]
    last_start = max(k for k, d in enumerate(stages)
                     if d["stage"] in lens and d["state"] == "start")
    first_done = min(k for k, d in enumerate(stages)
                     if d["stage"] in lens and d["state"] == "done")
    assert last_start < first_done, "an investigator finished before the others started"
    assert {d["group"] for d in stages if d["stage"] in lens} == {GROUP}, "one group id"
    assert {d["group"] for d in stages if d["stage"] not in lens} == {None}, \
        "only the investigators are grouped"

    assert all(d["result"] is None for d in starts), "a stage has no result yet at start"
    assert all(d["result"] == {"from": d["stage"]} for d in dones), "each stage's own result"
    assert [d["at"] for d in stages] == sorted(d["at"] for d in stages), "timestamps go forward"
    assert all(d["label"] for d in stages), "every stage carries a human label"

    # A stage that dies mid-pipeline must say so, and must not also say done.
    broken = asyncio.run(collect(_fake(explode_at="certify")))
    assert [n for n, _ in broken].count("error") == 1, broken
    assert "done" not in [n for n, _ in broken], "a failed autopsy never reports done"
    assert broken[-1][0] == "error" and "hung up" in broken[-1][1]["detail"], broken[-1]

    print(f"OK — {len(starts)} stages streamed in order, "
          f"{len(lens)} investigators overlapping under group '{GROUP}', "
          f"case delivered on done, model failure reported as error")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
