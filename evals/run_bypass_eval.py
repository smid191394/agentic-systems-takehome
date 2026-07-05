"""LLM-step accuracy eval for the bypass classifier (Layer B) -- NOT a pytest test.

pytest (tests/test_bypass.py) only checks that the wiring/fail-closed logic runs
correctly. This script is a real accuracy test report of a BypassClassifierClient
swept across several (name, temperature) configs -- the shape a real LLM client
comparison would take, scored against a golden set (evals/data/bypass_eval_set.json).

There is no real LLM in this project, so `OracleBypassClassifier` below stands
in for one -- it just reads the golden answer for each message and echoes it
back, unconditionally. Every oracle@tX row is therefore *expected* to score
100%, since temperature has no effect on a lookup table; this script exists to
exercise the config-sweep/report mechanics before a real client exists to plug
in. Swapping in a real BypassClassifierClient later only means adding entries
to CONFIGS; that is what would make temperature matter.

Run: uv run -m evals.run_bypass_eval
"""

import json
from dataclasses import dataclass
from pathlib import Path

from app.schemas.domain import BypassLLMResult

DATA_PATH = Path(__file__).resolve().parent / "data" / "bypass_eval_set.json"


@dataclass
class ClassificationMetrics:
    total: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int

    @property
    def accuracy(self) -> float:
        return (self.true_positive + self.true_negative) / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        denom = self.true_positive + self.false_positive
        return self.true_positive / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positive + self.false_negative
        return self.true_positive / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def classification_metrics(labels: list[tuple[bool, bool]]) -> ClassificationMetrics:
    """labels: list of (expected, predicted) suspicious booleans."""
    tp = sum(1 for exp, pred in labels if exp and pred)
    tn = sum(1 for exp, pred in labels if not exp and not pred)
    fp = sum(1 for exp, pred in labels if not exp and pred)
    fn = sum(1 for exp, pred in labels if exp and not pred)
    return ClassificationMetrics(len(labels), tp, tn, fp, fn)


def _row(name: str, values: list[str]) -> str:
    return f"{name:<16}" + "".join(f"{v:>7}" for v in values)


def format_metrics_table(rows: list[tuple[str, ClassificationMetrics]]) -> str:
    header = _row("config", ["n", "acc", "prec", "recall", "f1", "tp", "fp", "fn", "tn"])
    lines = [header, "-" * len(header)]
    for name, m in rows:
        values = [
            str(m.total),
            f"{m.accuracy:.1%}",
            f"{m.precision:.1%}",
            f"{m.recall:.1%}",
            f"{m.f1:.1%}",
            str(m.true_positive),
            str(m.false_positive),
            str(m.false_negative),
            str(m.true_negative),
        ]
        lines.append(_row(name, values))
    return "\n".join(lines)


class OracleBypassClassifier:
    """Always returns the golden `expect_suspicious` answer for the message."""

    def __init__(self, golden_cases: list[dict], temperature: float = 0.0) -> None:
        self._answers = {case["message"]: case["expect_suspicious"] for case in golden_cases}
        self.temperature = temperature  # unused; kept only for CONFIGS symmetry with a real client

    def classify(self, raw_message: str) -> BypassLLMResult:
        return BypassLLMResult(
            suspicious=self._answers[raw_message],
            reason="oracle placeholder -- no real model behind this",
            confidence=1.0,
        )


def build_configs(dataset: list[dict]) -> list[tuple[str, object]]:
    return [
        ("oracle@t0.0", lambda: OracleBypassClassifier(dataset, temperature=0.0)),
        ("oracle@t0.3", lambda: OracleBypassClassifier(dataset, temperature=0.3)),
        ("oracle@t0.7", lambda: OracleBypassClassifier(dataset, temperature=0.7)),
        ("oracle@t1.0", lambda: OracleBypassClassifier(dataset, temperature=1.0)),
    ]


def load_dataset() -> list[dict]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def evaluate(client, dataset: list[dict]) -> list[dict]:
    rows = []
    for case in dataset:
        predicted = client.classify(case["message"]).suspicious
        rows.append({**case, "predicted": predicted, "correct": predicted == case["expect_suspicious"]})
    return rows


def main() -> None:
    dataset = load_dataset()
    print(f"bypass eval set: {len(dataset)} cases\n")

    overall_rows = []
    for name, factory in build_configs(dataset):
        predictions = evaluate(factory(), dataset)
        overall = classification_metrics([(p["expect_suspicious"], p["predicted"]) for p in predictions])
        overall_rows.append((name, overall))

        misses = [p for p in predictions if not p["correct"]]
        if not misses:
            print(f"=== {name}: no misses ===")
            continue

        print(f"=== {name} ===")
        for miss in misses:
            print(
                f"  MISS [{miss['category']}] expected={miss['expect_suspicious']} "
                f"predicted={miss['predicted']}: {miss['message']}"
            )
        print()

    print("=== overall, by config ===")
    print(format_metrics_table(overall_rows))


if __name__ == "__main__":
    main()
