"""RunState — everything the harness accumulates during a single Agent Run."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.api import DraftPO, ToolCallRecord
from app.schemas.domain import BypassAssessment, LookupCatalogOutput, PlannerOutput


class RunState(BaseModel):
    run_id: str
    approval_status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
    action: Literal["CREATE_DRAFT_PO", "NEED_HUMAN_APPROVAL", "ASK_CLARIFICATION", "REJECT"] | None = None
    department: str
    planner_output: PlannerOutput | None = None
    catalog: LookupCatalogOutput | None = None
    bypass_assessment: BypassAssessment | None = None
    draft_po: DraftPO | None = None
    trace: list[dict] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)

    def record_tool_call(
        self,
        tool: str,
        status: Literal["success", "error"],
        detail: dict | None = None,
    ) -> None:
        self.tool_calls.append(ToolCallRecord(tool=tool, status=status))
        self.trace.append({"tool": tool, "status": status, **(detail or {})})
