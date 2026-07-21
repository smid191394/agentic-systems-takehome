"""check_policy — thin tool wrapper around PolicyEngine (registry entry point)."""

from app.policy.engine import PolicyEngine
from app.schemas.domain import CatalogItem, PolicyEvaluation


def check_policy(
    engine: PolicyEngine,
    *,
    department: str,
    item: CatalogItem,
    quantity: int,
) -> PolicyEvaluation:
    return engine.evaluate(department=department, item=item, quantity=quantity)
