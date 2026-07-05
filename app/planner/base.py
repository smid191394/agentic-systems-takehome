"""Planner Protocol — lets the harness swap RuleBasedPlanner <-> LLMPlanner freely."""

from typing import Protocol

from app.schemas.domain import PlannerOutput


class Planner(Protocol):
    def parse(self, department: str, raw_message: str) -> PlannerOutput: ...
