"""Public HTTP contract for POST /agent/run (+ optional approve endpoint)."""

from typing import Literal

from pydantic import BaseModel


class AgentRunRequest(BaseModel):
    user_id: str
    department: str
    message: str


class Decision(BaseModel):
    action: Literal["CREATE_DRAFT_PO", "NEED_HUMAN_APPROVAL", "ASK_CLARIFICATION", "REJECT"]
    risk_level: Literal["LOW", "HIGH"]
    requires_human_approval: bool
    reason: str


class DraftPO(BaseModel):
    item: str
    quantity: int
    estimated_total: float
    department: str


class ToolCallRecord(BaseModel):
    tool: str
    status: Literal["success", "error"]


class AgentRunResponse(BaseModel):
    run_id: str
    status: Literal["COMPLETED", "AWAITING_APPROVAL"]
    decision: Decision
    draft_po: DraftPO | None = None
    tool_calls: list[ToolCallRecord]


class ApproveRequest(BaseModel):
    approved: bool = True


class ApproveResponse(BaseModel):
    run_id: str
    approval_status: Literal["APPROVED", "REJECTED"]
