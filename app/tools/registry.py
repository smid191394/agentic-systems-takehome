"""ToolRegistry — single dispatch point for all tool calls.

Owns two guardrails:
  - every dispatch is recorded into RunState (trace + public tool_calls), so a
    tool raising an exception still shows up as a "error" ToolCallRecord.
  - Guardrail C: submit_to_erp is structurally unreachable until a run's
    approval_status is APPROVED. This check lives here (not in tools/erp.py)
    so it holds regardless of which Planner is producing plans.
"""

from app.harness.state import RunState
from app.policy.engine import PolicyEngine
from app.schemas.api import DraftPO
from app.schemas.domain import CatalogItem, LookupCatalogOutput, PolicyEvaluation
from app.tools import catalog as catalog_tool
from app.tools import draft as draft_tool
from app.tools import erp as erp_tool
from app.tools import policy_tool


class ApprovalRequiredError(Exception):
    """Raised when submit_to_erp is dispatched before a run has been approved."""


class ToolRegistry:
    def __init__(self, catalog_items: list[CatalogItem], policy_engine: PolicyEngine) -> None:
        self._catalog_items = catalog_items
        self._policy_engine = policy_engine

    def lookup_catalog(self, state: RunState, *, item_query: str, raw_message: str) -> LookupCatalogOutput:
        try:
            result = catalog_tool.lookup_catalog(
                item_query=item_query, raw_message=raw_message, catalog_items=self._catalog_items
            )
        except Exception:
            state.record_tool_call("lookup_catalog", "error")
            raise
        state.record_tool_call("lookup_catalog", "success", {"result": result.result})
        return result

    def check_policy(
        self,
        state: RunState,
        *,
        raw_message: str,
        department: str,
        item: CatalogItem,
        quantity: int,
    ) -> PolicyEvaluation:
        try:
            evaluation = policy_tool.check_policy(
                self._policy_engine,
                raw_message=raw_message,
                department=department,
                item=item,
                quantity=quantity,
            )
        except Exception:
            state.record_tool_call("check_policy", "error")
            raise
        state.bypass_assessment = evaluation.bypass
        state.policy_reasons = evaluation.reasons
        state.record_tool_call(
            "check_policy",
            "success",
            {"action": evaluation.action, "reasons": evaluation.reasons},
        )
        return evaluation

    def create_draft_po(
        self,
        state: RunState,
        *,
        item: CatalogItem,
        quantity: int,
        department: str,
    ) -> DraftPO:
        try:
            draft = draft_tool.create_draft_po(item=item, quantity=quantity, department=department)
        except Exception:
            state.record_tool_call("create_draft_po", "error")
            raise
        state.draft_po = draft
        state.record_tool_call("create_draft_po", "success")
        return draft

    def submit_to_erp(self, state: RunState) -> dict:
        if state.approval_status != "APPROVED":
            state.record_tool_call("submit_to_erp", "error")
            raise ApprovalRequiredError(
                f"run {state.run_id} is not approved (approval_status={state.approval_status})"
            )
        result = erp_tool.submit_to_erp(state.run_id)
        state.record_tool_call("submit_to_erp", "success")
        return result
