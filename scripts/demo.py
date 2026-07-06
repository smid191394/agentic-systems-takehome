"""Demo — runs the 11 canonical cases (5 official + 6 custom) in tests/data/requests.json
through the same harness wiring as the live API, and prints each decision.

An alternative to curl for eyeballing end-to-end behavior; see docs/README.md's
"Demo / 驗證建議" section.

Run: uv run scripts/demo.py
"""

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from app.api.routes import build_harness  # noqa: E402
from app.schemas.api import AgentRunRequest  # noqa: E402

REQUESTS_PATH = _PROJECT_ROOT / "tests" / "data" / "requests.json"


def main() -> None:
    harness = build_harness()
    cases = json.loads(REQUESTS_PATH.read_text(encoding="utf-8"))

    passed = 0
    for case in cases:
        request = AgentRunRequest(
            user_id=case["user_id"], department=case["department"], message=case["message"]
        )
        response = harness.run(request)
        ok = response.decision.action == case["expected_behavior"]
        passed += ok

        print(f"[{'OK' if ok else 'FAIL'}] {case['id']} ({case['source']})")
        print(f"  message:  {case['message']}")
        print(f"  expected: {case['expected_behavior']}")
        print(f"  actual:   {response.decision.action} (risk={response.decision.risk_level})")
        print(f"  status:   {response.status}")
        print(f"  reason:   {response.decision.reason}")
        if response.draft_po is not None:
            print(f"  draft_po: {response.draft_po.model_dump()}")
        print()

    print(f"{passed}/{len(cases)} cases matched expected_behavior")


if __name__ == "__main__":
    main()
