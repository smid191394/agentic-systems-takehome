"""PolicyEngine — the only component allowed to produce a final decision action.

Deterministic rule table (bypass already resolved by BypassEvaluator):
  1a. bypass pattern hit           -> REJECT
  1b. bypass LLM suspicious/failed -> NEED_HUMAN_APPROVAL
  2.  restricted category          -> NEED_HUMAN_APPROVAL
  3.  amount > approval_threshold  -> NEED_HUMAN_APPROVAL
  4.  amount > department budget (or department unknown) -> NEED_HUMAN_APPROVAL
  5.  otherwise                    -> CREATE_DRAFT_PO

When multiple of rules 2-4 fire, all reasons are aggregated (not just the first).
"""

from app.policy.bypass import BypassEvaluator
from app.schemas.domain import CatalogItem, DepartmentBudget, PoliciesConfig, PolicyEvaluation


class PolicyEngine:
    def __init__(
        self,
        policies: PoliciesConfig,
        budgets: dict[str, DepartmentBudget],
        bypass_evaluator: BypassEvaluator,
    ) -> None:
        self._policies = policies
        self._budgets = budgets
        self._bypass_evaluator = bypass_evaluator

    def evaluate(
        self,
        *,
        raw_message: str,
        department: str,
        item: CatalogItem,
        quantity: int,
    ) -> PolicyEvaluation:
        bypass = self._bypass_evaluator.evaluate(raw_message)

        if bypass.pattern_hit:
            return PolicyEvaluation(action="REJECT", reasons=["bypass_pattern_detected"], bypass=bypass)

        if bypass.llm is not None and bypass.llm.suspicious:
            return PolicyEvaluation(
                action="NEED_HUMAN_APPROVAL", reasons=["bypass_llm_suspicious"], bypass=bypass
            )

        if bypass.llm is None and bypass.llm_error is not None:
            return PolicyEvaluation(
                action="NEED_HUMAN_APPROVAL", reasons=["bypass_llm_unavailable"], bypass=bypass
            )

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
        return PolicyEvaluation(
            action=action, reasons=reasons, bypass=bypass, estimated_total=estimated_total
        )
