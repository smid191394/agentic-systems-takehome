"""LLM-step accuracy eval for the planner (item/quantity/budget extraction) -- NOT a pytest test.

This script is a real accuracy test report of a Planner swept across several
(name, temperature) configs -- the shape a real LLM client comparison would
take. Ground truth is defined functionally: does parse() + lookup_catalog()
resolve to the expected catalog item (or the expected not_found/ambiguous
outcome), and are quantity/budget_cap_usd extracted correctly -- so the golden
set doesn't require exact-string equality on item_query (no two
implementations would phrase it identically).

There is no real LLM in this project, so `OraclePlanner` below stands in for
one -- it just reads the golden quantity/budget/item-presence for each message
and echoes it back, unconditionally. Every oracle@tX row is therefore
*expected* to score 100%, since temperature has no effect on a lookup table;
this script exists to exercise the config-sweep/report mechanics before a real
client exists to plug in. Swapping in a real Planner later only means adding
entries to CONFIGS; that is what would make temperature matter.

Run: uv run -m evals.run_planner_eval
"""

import json
from pathlib import Path

from app.config import get_settings
from app.fixtures_loader import load_fixtures
from app.schemas.domain import PlannerOutput
from app.tools.catalog import lookup_catalog

DATA_PATH = Path(__file__).resolve().parent / "data" / "planner_eval_set.json"


class OraclePlanner:
    """Always returns the golden quantity/budget/item-presence for the message."""

    def __init__(self, golden_cases: list[dict], temperature: float = 0.0) -> None:
        self._answers = {case["message"]: case for case in golden_cases}
        self.temperature = temperature  # unused; kept only for CONFIGS symmetry with a real client

    def parse(self, department: str, raw_message: str) -> PlannerOutput:
        golden = self._answers[raw_message]
        return PlannerOutput(
            department=department,
            raw_message=raw_message,
            item_query=raw_message if golden["expected_item_present"] else None,
            quantity=golden["expected_quantity"],
            budget_cap_usd=golden["expected_budget_cap_usd"],
        )


def build_configs(dataset: list[dict]) -> list[tuple[str, object]]:
    return [
        ("oracle@t0.0", lambda: OraclePlanner(dataset, temperature=0.0)),
        ("oracle@t0.3", lambda: OraclePlanner(dataset, temperature=0.3)),
        ("oracle@t0.7", lambda: OraclePlanner(dataset, temperature=0.7)),
        ("oracle@t1.0", lambda: OraclePlanner(dataset, temperature=1.0)),
    ]


def load_dataset() -> list[dict]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _resolve(item_query: str, raw_message: str, catalog_items) -> str:
    result = lookup_catalog(item_query=item_query, raw_message=raw_message, catalog_items=catalog_items)
    if result.result == "found":
        return f"found:{result.item_id}"
    return result.result


def evaluate(planner, dataset: list[dict], catalog_items) -> list[dict]:
    rows = []
    for case in dataset:
        output = planner.parse(case["department"], case["message"])

        quantity_ok = output.quantity == case["expected_quantity"]
        budget_ok = output.budget_cap_usd == case["expected_budget_cap_usd"]

        if case["expected_item_present"]:
            item_present_ok = output.item_query is not None
            resolution = (
                _resolve(output.item_query or "", case["message"], catalog_items) if item_present_ok else None
            )
            resolution_ok = item_present_ok and resolution == case["expected_resolution"]
        else:
            item_present_ok = output.item_query is None
            resolution = None
            resolution_ok = item_present_ok

        rows.append(
            {
                **case,
                "actual_quantity": output.quantity,
                "actual_budget_cap_usd": output.budget_cap_usd,
                "actual_item_query": output.item_query,
                "actual_resolution": resolution,
                "quantity_ok": quantity_ok,
                "budget_ok": budget_ok,
                "resolution_ok": resolution_ok,
                "fully_correct": quantity_ok and budget_ok and resolution_ok,
            }
        )
    return rows


def _rate(rows: list[dict], key: str) -> float:
    return sum(1 for r in rows if r[key]) / len(rows) if rows else 0.0


def main() -> None:
    fixtures = load_fixtures(get_settings().fixtures_dir)
    dataset = load_dataset()
    print(f"planner eval set: {len(dataset)} cases\n")

    summary_rows = []
    for name, factory in build_configs(dataset):
        rows = evaluate(factory(), dataset, fixtures.catalog)
        summary_rows.append(
            (
                name,
                _rate(rows, "quantity_ok"),
                _rate(rows, "budget_ok"),
                _rate(rows, "resolution_ok"),
                _rate(rows, "fully_correct"),
            )
        )

        misses = [row for row in rows if not row["fully_correct"]]
        if not misses:
            print(f"=== {name}: no misses (fully_correct_rate=100.0%) ===")
            continue

        print(f"=== {name} ===")
        for row in misses:
            print(
                f"  MISS [{row['category']}] {row['id']}: quantity_ok={row['quantity_ok']} "
                f"budget_ok={row['budget_ok']} resolution_ok={row['resolution_ok']} "
                f"(actual quantity={row['actual_quantity']!r} budget={row['actual_budget_cap_usd']!r} "
                f"item_query={row['actual_item_query']!r} resolution={row['actual_resolution']!r}) "
                f"-- {row['message']}"
            )
        print(
            f"  quantity_accuracy={_rate(rows, 'quantity_ok'):.1%}  "
            f"budget_accuracy={_rate(rows, 'budget_ok'):.1%}  "
            f"resolution_accuracy={_rate(rows, 'resolution_ok'):.1%}  "
            f"fully_correct_rate={_rate(rows, 'fully_correct'):.1%}"
        )
        print()

    header = f"{'config':<15}{'quantity':>10}{'budget':>10}{'resolution':>12}{'fully_correct':>15}"
    print("=== summary, by config ===")
    print(header)
    print("-" * len(header))
    for name, q, b, r, fc in summary_rows:
        print(f"{name:<15}{q:>10.1%}{b:>10.1%}{r:>12.1%}{fc:>15.1%}")


if __name__ == "__main__":
    main()
