"""Internal models: fixtures, planner output, tool I/O, bypass, policy evaluation.

These are not part of the public HTTP contract (see schemas/api.py) — they are
the shapes the harness/tools/policy layers pass between each other.
"""

from typing import Literal

from pydantic import BaseModel, Field


class CatalogItem(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    unit_price: float
    category: Literal["software", "hardware", "enterprise_software"]


class PoliciesConfig(BaseModel):
    approval_threshold_usd: float
    restricted_categories: list[str]
    rules: list[dict] = Field(default_factory=list)


class DepartmentBudget(BaseModel):
    remaining_budget_usd: float


class PlannerOutput(BaseModel):
    department: str
    raw_message: str
    item_query: str | None = None
    quantity: int | None = None
    budget_cap_usd: float | None = None


class LookupCatalogInput(BaseModel):
    item_query: str
    raw_message: str


class LookupCatalogOutput(BaseModel):
    result: Literal["found", "not_found", "ambiguous"]
    item_id: str | None = None
    name: str | None = None
    unit_price: float | None = None
    category: str | None = None
    matched_item_ids: list[str] | None = None


class BypassLLMResult(BaseModel):
    suspicious: bool
    reason: str
    confidence: float | None = None


class BypassAssessment(BaseModel):
    pattern_hit: bool
    llm_called: bool = False
    llm: BypassLLMResult | None = None
    llm_skipped_reason: Literal["pattern_hit"] | None = None
    llm_error: str | None = None


class PolicyEvaluation(BaseModel):
    action: Literal["CREATE_DRAFT_PO", "NEED_HUMAN_APPROVAL", "REJECT"]
    reasons: list[str] = Field(default_factory=list)
    bypass: BypassAssessment
    estimated_total: float | None = None
