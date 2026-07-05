"""Placeholder for a real-LLM planner (P2/bonus) — demonstrates Planner is swappable.

Not wired into the default harness; app/config.py's `planner` setting exists to
select this once implemented. The bypass semantic check (policy/bypass.py) is a
separate LLM call and does not depend on this class.
"""

from app.schemas.domain import PlannerOutput


class LLMPlanner:
    def __init__(self, client: object | None = None) -> None:
        self._client = client

    def parse(self, department: str, raw_message: str) -> PlannerOutput:
        raise NotImplementedError("LLMPlanner is a placeholder for a future extension")
