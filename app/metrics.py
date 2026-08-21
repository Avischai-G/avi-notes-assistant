"""Deterministic measurements over Coroner case files.

Run the definition self-check and measure the public and private case sets:
    python -m app.metrics
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import itertools
import json
from pathlib import Path
import sys


LENSES = ("sequence", "counterfactual", "alternative")
PUBLIC_CASES = Path("data/cases")
PRIVATE_CASES = Path(
    "/Users/avischaigrau/Documents/Agentonomy-Files/notes/income-campaign/"
    "coroner-private/real-cases"
)


@dataclass(frozen=True)
class Metrics:
    cases: int
    hypotheses_proposed: int
    hypotheses_killed_by_majority: int
    non_unanimous_hypotheses: int
    pairwise_lens_disagreements: int
    pairwise_lens_comparisons: int
    cases_with_non_unanimous_hypothesis: int
    certified_prior_disagreements: int
    silent_stops: int
    silent_rate: float
    mean_progress: float
    steps_planned: int
    steps_banked: int
    steps_abandoned: int

    def as_dict(self) -> dict:
        return asdict(self)


def measure_cases(cases: list[dict]) -> Metrics:
    proposed = killed = non_unanimous = pairwise = cases_with_disagreement = 0
    prior_disagreements = silent = planned = banked = 0
    progress = []

    for index, case in enumerate(cases):
        name = str(case.get("run_id") or index)
        hypotheses = case.get("hypotheses") or []
        causes = [h.get("cause") for h in hypotheses]
        if len(causes) != len(set(causes)) or any(not cause for cause in causes):
            raise ValueError(f"{name}: hypotheses must have distinct non-empty causes")

        verdicts = case.get("verdicts") or {}
        by_lens = {}
        for lens in LENSES:
            rows = verdicts.get(lens)
            if not isinstance(rows, list):
                raise ValueError(f"{name}: missing verdict list for {lens}")
            mapped = {row.get("cause"): row.get("survives") for row in rows}
            if len(mapped) != len(rows) or set(mapped) != set(causes):
                raise ValueError(f"{name}: {lens} verdicts do not match hypotheses")
            if any(type(value) is not bool for value in mapped.values()):
                raise ValueError(f"{name}: {lens} verdicts must use boolean survives values")
            by_lens[lens] = mapped

        case_disagreed = False
        for cause in causes:
            values = [by_lens[lens][cause] for lens in LENSES]
            survives = sum(values)
            proposed += 1
            if survives <= 1:
                killed += 1
            if 0 < survives < len(LENSES):
                non_unanimous += 1
                case_disagreed = True
            pairwise += sum(a != b for a, b in itertools.combinations(values, 2))
        cases_with_disagreement += case_disagreed

        certified = (case.get("certificate") or {}).get("cause")
        prior = case.get("prior_cause")
        if certified and prior and certified != prior:
            prior_disagreements += 1

        evidence = case.get("evidence") or {}
        silent += bool(evidence.get("silent"))
        fraction = float(evidence.get("progress") or 0.0)
        count = int(evidence.get("steps_planned") or 0)
        if (certified or prior) != "USER_ABORT":   # a run stopped on purpose did not die
            progress.append(fraction)
        planned += count
        banked += round(fraction * count)

    count = len(cases)
    return Metrics(
        cases=count,
        hypotheses_proposed=proposed,
        hypotheses_killed_by_majority=killed,
        non_unanimous_hypotheses=non_unanimous,
        pairwise_lens_disagreements=pairwise,
        pairwise_lens_comparisons=proposed * 3,
        cases_with_non_unanimous_hypothesis=cases_with_disagreement,
        certified_prior_disagreements=prior_disagreements,
        silent_stops=silent,
        silent_rate=silent / count if count else 0.0,
        mean_progress=sum(progress) / len(progress) if progress else 0.0,
        steps_planned=planned,
        steps_banked=banked,
        steps_abandoned=planned - banked,
    )


def measure(path: Path | str) -> Metrics:
    directory = Path(path)
    files = sorted(directory.glob("*.json"))
    if not files:
        raise ValueError(f"no case files found in {directory}")
    return measure_cases([json.loads(file.read_text()) for file in files])


def _fixture() -> list[dict]:
    causes = ("all-survive", "split-survive", "split-refuse", "all-refuse")
    survival = {
        "sequence": (True, True, True, False),
        "counterfactual": (True, True, False, False),
        "alternative": (True, False, False, False),
    }
    return [{
        "run_id": "definition-check",
        "prior_cause": "RULE_PRIOR",
        "hypotheses": [{"cause": cause} for cause in causes],
        "verdicts": {
            lens: [{"cause": cause, "survives": value}
                   for cause, value in zip(causes, values)]
            for lens, values in survival.items()
        },
        "certificate": {"cause": "CERTIFIED"},
        "evidence": {"silent": True, "progress": 0.5, "steps_planned": 4},
    }]


def demo() -> None:
    result = measure_cases(_fixture())
    assert result.hypotheses_proposed == 4
    assert result.hypotheses_killed_by_majority == 2
    assert result.non_unanimous_hypotheses == 2
    assert result.pairwise_lens_disagreements == 4
    assert result.pairwise_lens_comparisons == 12
    assert result.cases_with_non_unanimous_hypothesis == 1
    assert result.certified_prior_disagreements == 1
    assert (result.steps_planned, result.steps_banked, result.steps_abandoned) == (4, 2, 2)
    print("OK — unanimous survive/refuse verdicts are agreement; split verdicts are disagreement")


def _ratio(value: int, total: int) -> str:
    return f"{value}/{total} = {value / total:.4%}" if total else f"{value}/0 = n/a"


def print_metrics(path: Path, result: Metrics) -> None:
    print(f"\n{path}:")
    print(f"  cases: {result.cases}")
    print(f"  hypotheses proposed: {result.hypotheses_proposed}")
    print("  hypotheses killed by majority: "
          + _ratio(result.hypotheses_killed_by_majority, result.hypotheses_proposed))
    print("  non-unanimous hypotheses: "
          + _ratio(result.non_unanimous_hypotheses, result.hypotheses_proposed))
    print("  pairwise lens disagreement: "
          + _ratio(result.pairwise_lens_disagreements, result.pairwise_lens_comparisons))
    print("  cases with a non-unanimous hypothesis: "
          + _ratio(result.cases_with_non_unanimous_hypothesis, result.cases))
    print("  certified cause differs from rule prior: "
          + _ratio(result.certified_prior_disagreements, result.cases))
    print("  silent stops: " + _ratio(result.silent_stops, result.cases))
    print(f"  mean progress: {result.mean_progress:.4%} (of runs that did not stop on purpose)")
    print(f"  steps planned/banked/abandoned: {result.steps_planned}/"
          f"{result.steps_banked}/{result.steps_abandoned}")


def main(args: list[str] | None = None) -> int:
    demo()
    paths = [Path(arg) for arg in (args if args is not None else sys.argv[1:])]
    for path in paths or [PUBLIC_CASES, PRIVATE_CASES]:
        print_metrics(path, measure(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
