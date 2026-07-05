"""Planner Protocol — a real LLM-backed planner could implement this and drop in
without changing AgentHarness; the Protocol is what makes it swappable, not a
pre-existing stub implementation."""

from typing import Protocol

from app.schemas.domain import PlannerOutput


class Planner(Protocol):
    def parse(self, department: str, raw_message: str) -> PlannerOutput: ...
