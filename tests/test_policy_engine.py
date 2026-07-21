"""PolicyEngine — amount/budget boundaries, unknown department, reason aggregation.

Bypass detection has moved to BypassGate (see tests/test_bypass_gate.py) — it
runs before PolicyEngine is ever called, so PolicyEngine.evaluate() no longer
takes raw_message or produces REJECT.

Uses synthetic policies/budgets/items (not fixtures/*.json) so amount/budget
boundaries land on exact numbers instead of being at the mercy of catalog unit
prices.
"""

from app.policy.engine import PolicyEngine
from app.schemas.domain import CatalogItem, DepartmentBudget, PoliciesConfig


def _engine(*, threshold: float, restricted: list[str], budgets: dict[str, float]) -> PolicyEngine:
    policies = PoliciesConfig(approval_threshold_usd=threshold, restricted_categories=restricted)
    budget_map = {dept: DepartmentBudget(remaining_budget_usd=amount) for dept, amount in budgets.items()}
    return PolicyEngine(policies, budget_map)


def _item(*, unit_price: float, category: str = "software") -> CatalogItem:
    return CatalogItem(id="item_x", name="Widget", unit_price=unit_price, category=category)


def test_amount_exactly_at_threshold_is_allowed():
    engine = _engine(threshold=5000, restricted=[], budgets={"eng": 999_999})
    item = _item(unit_price=5000)

    result = engine.evaluate(department="eng", item=item, quantity=1)

    assert result.action == "CREATE_DRAFT_PO"
    assert result.reasons == []


def test_amount_one_over_threshold_needs_approval():
    engine = _engine(threshold=5000, restricted=[], budgets={"eng": 999_999})
    item = _item(unit_price=5001)

    result = engine.evaluate(department="eng", item=item, quantity=1)

    assert result.action == "NEED_HUMAN_APPROVAL"
    assert result.reasons == ["amount_exceeds_threshold"]


def test_amount_exactly_equal_to_remaining_budget_is_allowed():
    engine = _engine(threshold=999_999, restricted=[], budgets={"eng": 1000})
    item = _item(unit_price=1000)

    result = engine.evaluate(department="eng", item=item, quantity=1)

    assert result.action == "CREATE_DRAFT_PO"
    assert result.reasons == []


def test_amount_one_over_remaining_budget_needs_approval():
    engine = _engine(threshold=999_999, restricted=[], budgets={"eng": 999})
    item = _item(unit_price=1000)

    result = engine.evaluate(department="eng", item=item, quantity=1)

    assert result.action == "NEED_HUMAN_APPROVAL"
    assert result.reasons == ["exceeds_department_budget"]


def test_unknown_department_fails_closed_to_approval():
    engine = _engine(threshold=999_999, restricted=[], budgets={"eng": 999_999})
    item = _item(unit_price=10)

    result = engine.evaluate(department="sales", item=item, quantity=1)

    assert result.action == "NEED_HUMAN_APPROVAL"
    assert result.reasons == ["unknown_department_budget"]


def test_restricted_category_alone_needs_approval():
    engine = _engine(threshold=999_999, restricted=["hardware"], budgets={"eng": 999_999})
    item = _item(unit_price=10, category="hardware")

    result = engine.evaluate(department="eng", item=item, quantity=1)

    assert result.action == "NEED_HUMAN_APPROVAL"
    assert result.reasons == ["restricted_category:hardware"]


def test_reason_aggregation_across_category_and_amount():
    engine = _engine(threshold=5000, restricted=["hardware"], budgets={"eng": 999_999})
    item = _item(unit_price=6000, category="hardware")

    result = engine.evaluate(department="eng", item=item, quantity=1)

    assert result.action == "NEED_HUMAN_APPROVAL"
    assert result.reasons == ["restricted_category:hardware", "amount_exceeds_threshold"]


def test_reason_aggregation_across_all_three_rules():
    engine = _engine(threshold=5000, restricted=["hardware"], budgets={"eng": 100})
    item = _item(unit_price=6000, category="hardware")

    result = engine.evaluate(department="eng", item=item, quantity=1)

    assert result.action == "NEED_HUMAN_APPROVAL"
    assert result.reasons == [
        "restricted_category:hardware",
        "amount_exceeds_threshold",
        "exceeds_department_budget",
    ]


def test_no_rules_fire_creates_draft_po():
    engine = _engine(threshold=5000, restricted=["hardware"], budgets={"eng": 5000})
    item = _item(unit_price=100, category="software")

    result = engine.evaluate(department="eng", item=item, quantity=1)

    assert result.action == "CREATE_DRAFT_PO"
    assert result.reasons == []
    assert result.estimated_total == 100
