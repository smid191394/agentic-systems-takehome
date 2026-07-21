"""check_bypass — thin tool wrapper around BypassGate (registry entry point)."""

from app.policy.bypass import BypassGate
from app.schemas.domain import BypassEvaluation


def check_bypass(gate: BypassGate, *, raw_message: str) -> BypassEvaluation:
    return gate.check(raw_message)
