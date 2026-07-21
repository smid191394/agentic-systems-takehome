"""PolicyEngine — the only component allowed to produce a CREATE_DRAFT_PO /
NEED_HUMAN_APPROVAL decision from category/amount/budget rules.

Bypass detection (policy_004) is resolved earlier by BypassGate, at harness
step 2, right after RunState init — a REJECT/NEED_HUMAN_APPROVAL verdict
there short-circuits the run before PolicyEngine is ever called. By the time
PolicyEngine.evaluate() runs, bypass has already cleared.

Deterministic rule table:
  1. restricted category          -> NEED_HUMAN_APPROVAL
  2. amount > approval_threshold  -> NEED_HUMAN_APPROVAL
  3. amount > department budget (or department unknown) -> NEED_HUMAN_APPROVAL
  4. otherwise                    -> CREATE_DRAFT_PO

When multiple of rules 1-3 fire, all reasons are aggregated (not just the first).
"""

from app.schemas.domain import CatalogItem, DepartmentBudget, PoliciesConfig, PolicyEvaluation


class PolicyEngine:
    def __init__(
        self,
        policies: PoliciesConfig,
        budgets: dict[str, DepartmentBudget],
    ) -> None:
        self._policies = policies
        self._budgets = budgets

    def evaluate(
        self,
        *,
        department: str,
        item: CatalogItem,
        quantity: int,
    ) -> PolicyEvaluation:
        estimated_total = quantity * item.unit_price
        reasons: list[str] = []

        if item.category in self._policies.restricted_categories:
            reasons.append(f"restricted_category:{item.category}")

        if estimated_total > self._policies.approval_threshold_usd:
            reasons.append("amount_exceeds_threshold")

        budget = self._budgets.get(department)
        if budget is None:
            reasons.append("unknown_department_budget")
        elif estimated_total > budget.remaining_budget_usd:
            reasons.append("exceeds_department_budget")

        action = "NEED_HUMAN_APPROVAL" if reasons else "CREATE_DRAFT_PO"
        return PolicyEvaluation(action=action, reasons=reasons, estimated_total=estimated_total)
