"""ToolRegistry — single dispatch point for all tool calls.

Every dispatch is recorded into RunState (trace + public tool_calls), so a
tool raising an exception still shows up as an "error" ToolCallRecord.
"""

from app.harness.state import RunState
from app.policy.bypass import BypassGate
from app.policy.engine import PolicyEngine
from app.schemas.api import DraftPO
from app.schemas.domain import BypassEvaluation, CatalogItem, LookupCatalogOutput, PolicyEvaluation
from app.tools import bypass_tool
from app.tools import catalog as catalog_tool
from app.tools import draft as draft_tool
from app.tools import policy_tool


class ToolRegistry:
    def __init__(
        self,
        catalog_items: list[CatalogItem],
        policy_engine: PolicyEngine,
        bypass_gate: BypassGate,
    ) -> None:
        self._catalog_items = catalog_items
        self._policy_engine = policy_engine
        self._bypass_gate = bypass_gate

    def check_bypass(self, state: RunState, *, raw_message: str) -> BypassEvaluation:
        try:
            evaluation = bypass_tool.check_bypass(self._bypass_gate, raw_message=raw_message)
        except Exception:
            state.record_tool_call("check_bypass", "error")
            raise
        state.bypass_assessment = evaluation.assessment
        state.record_tool_call(
            "check_bypass",
            "success",
            {"action": evaluation.action, "reasons": evaluation.reasons},
        )
        return evaluation

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
        department: str,
        item: CatalogItem,
        quantity: int,
    ) -> PolicyEvaluation:
        try:
            evaluation = policy_tool.check_policy(
                self._policy_engine,
                department=department,
                item=item,
                quantity=quantity,
            )
        except Exception:
            state.record_tool_call("check_policy", "error")
            raise
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
