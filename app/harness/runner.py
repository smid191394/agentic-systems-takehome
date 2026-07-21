"""AgentHarness — the fixed 9-step Agent Loop.

    1. init RunState
    2. check_bypass (unconditional; two layers: pattern, then semantic
       classifier) -> REJECT / NEED_HUMAN_APPROVAL -> return early, before the
       Planner ever sees the message
    3. Planner.parse -> PlannerOutput
    4. harness validation (missing item/quantity -> ASK; qty<=0 -> REJECT)
    5. lookup_catalog -> found / not_found / ambiguous (not_found/ambiguous -> ASK)
    6. check_policy (unconditional; category/amount/budget rules — bypass
       already resolved in step 2)
    7. NEED_HUMAN_APPROVAL -> return early
    8. create_draft_po
    9. build + schema-validate AgentRunResponse

The Planner never chooses which tool runs next or what the final action is —
step order is fixed by this class, and only BypassGate (step 2) / PolicyEngine
(step 6) produce REJECT/NEED_HUMAN_APPROVAL/CREATE_DRAFT_PO. This is the
Approval Boundary: even a compromised/malicious planner output cannot skip
check_bypass/check_policy or reach create_draft_po without passing them.
Putting the bypass gate first means an obviously dangerous message is rejected
before spending any Planner/catalog/policy work on it.
"""

import uuid
from typing import Literal

from app.harness.state import RunState
from app.planner.base import Planner
from app.schemas.api import AgentRunRequest, AgentRunResponse, Decision, DraftPO
from app.schemas.domain import CatalogItem
from app.tools.registry import ToolRegistry

_REASON_MESSAGES = {
    "missing_item": "Could not identify a requested item in the message.",
    "missing_quantity": "Quantity was not specified.",
    "invalid_quantity": "Quantity must be a positive number.",
    "item_not_found": "Requested item does not match any catalog entry.",
    "item_ambiguous": "Requested item matches multiple catalog entries.",
    "bypass_pattern_detected": "Message explicitly requests bypassing approval/policy.",
    "bypass_llm_suspicious": "Semantic review flagged a possible attempt to bypass approval.",
    "bypass_llm_unavailable": "Bypass risk could not be verified; failing closed to human approval.",
    "amount_exceeds_threshold": "Estimated total exceeds the approval threshold.",
    "unknown_department_budget": "Department has no known budget on file.",
    "exceeds_department_budget": "Estimated total exceeds the department's remaining budget.",
    "policy_check_passed": "Request complies with policy.",
}

_RISK_BY_ACTION: dict[str, tuple[Literal["LOW", "HIGH"], bool]] = {
    "CREATE_DRAFT_PO": ("LOW", False),
    "NEED_HUMAN_APPROVAL": ("HIGH", True),
    "ASK_CLARIFICATION": ("LOW", False),
    "REJECT": ("HIGH", True),
}


def _reason_message(code: str) -> str:
    if code.startswith("restricted_category:"):
        category = code.split(":", 1)[1]
        return f"Item category '{category}' requires human approval."
    return _REASON_MESSAGES.get(code, code)


def _build_decision(action: str, reasons: list[str]) -> Decision:
    risk_level, requires_approval = _RISK_BY_ACTION[action]
    reason_text = (
        "; ".join(_reason_message(code) for code in reasons)
        if reasons
        else _reason_message("policy_check_passed")
    )
    return Decision(
        action=action, risk_level=risk_level, requires_human_approval=requires_approval, reason=reason_text
    )


class AgentHarness:
    def __init__(
        self,
        planner: Planner,
        catalog_items: list[CatalogItem],
        tool_registry: ToolRegistry,
    ) -> None:
        self._planner = planner
        self._catalog_items = catalog_items
        self._tools = tool_registry
        self._runs: dict[str, RunState] = {}

    def get_run(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        state = RunState(run_id=str(uuid.uuid4()), department=request.department)
        self._runs[state.run_id] = state

        bypass_evaluation = self._tools.check_bypass(state, raw_message=request.message)
        if bypass_evaluation.action != "PASS":
            return self._finish(state, bypass_evaluation.action, bypass_evaluation.reasons)

        planner_output = self._planner.parse(request.department, request.message)
        state.planner_output = planner_output

        if planner_output.item_query is None:
            return self._finish(state, "ASK_CLARIFICATION", ["missing_item"])
        if planner_output.quantity is None:
            return self._finish(state, "ASK_CLARIFICATION", ["missing_quantity"])
        if planner_output.quantity <= 0:
            return self._finish(state, "REJECT", ["invalid_quantity"])

        catalog_result = self._tools.lookup_catalog(
            state, item_query=planner_output.item_query, raw_message=request.message
        )
        state.catalog = catalog_result

        if catalog_result.result == "not_found":
            return self._finish(state, "ASK_CLARIFICATION", ["item_not_found"])
        if catalog_result.result == "ambiguous":
            return self._finish(state, "ASK_CLARIFICATION", ["item_ambiguous"])

        item = next(i for i in self._catalog_items if i.id == catalog_result.item_id)

        evaluation = self._tools.check_policy(
            state,
            department=request.department,
            item=item,
            quantity=planner_output.quantity,
        )

        if evaluation.action == "NEED_HUMAN_APPROVAL":
            return self._finish(state, evaluation.action, evaluation.reasons)

        draft = self._tools.create_draft_po(
            state,
            item=item,
            quantity=planner_output.quantity,
            department=request.department,
        )
        return self._finish(state, "CREATE_DRAFT_PO", [], draft_po=draft)

    def _finish(
        self,
        state: RunState,
        action: str,
        reasons: list[str],
        draft_po: DraftPO | None = None,
    ) -> AgentRunResponse:
        state.action = action
        if action == "REJECT":
            state.approval_status = "REJECTED"

        decision = _build_decision(action, reasons)
        status = "AWAITING_APPROVAL" if action == "NEED_HUMAN_APPROVAL" else "COMPLETED"
        return AgentRunResponse(
            run_id=state.run_id,
            status=status,
            decision=decision,
            draft_po=draft_po,
            tool_calls=state.tool_calls,
        )
