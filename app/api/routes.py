"""POST /agent/run (+ optional approve endpoint) — wires the harness, no business logic here."""

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.fixtures_loader import load_fixtures
from app.harness.runner import AgentHarness
from app.planner.rule_based import RuleBasedPlanner
from app.policy.bypass import BypassEvaluator, RuleBasedBypassClassifier
from app.policy.engine import PolicyEngine
from app.schemas.api import AgentRunRequest, AgentRunResponse, ApproveRequest, ApproveResponse
from app.tools.registry import ToolRegistry

router = APIRouter()


@lru_cache
def build_harness() -> AgentHarness:
    """Wires the harness stack. Also reused by scripts/demo.py so the demo runs against
    the exact same construction as the live API, not a hand-rolled copy."""
    settings = get_settings()
    fixtures = load_fixtures(settings.fixtures_dir)

    bypass_evaluator = BypassEvaluator(RuleBasedBypassClassifier())
    policy_engine = PolicyEngine(fixtures.policies, fixtures.budgets, bypass_evaluator)
    tool_registry = ToolRegistry(fixtures.catalog, policy_engine)
    planner = RuleBasedPlanner()

    return AgentHarness(planner, fixtures.catalog, tool_registry)


def get_harness() -> AgentHarness:
    return build_harness()


@router.post("/agent/run", response_model=AgentRunResponse)
def run_agent(request: AgentRunRequest, harness: AgentHarness = Depends(get_harness)) -> AgentRunResponse:
    return harness.run(request)


@router.post("/agent/runs/{run_id}/approve", response_model=ApproveResponse)
def approve_run(
    run_id: str,
    body: ApproveRequest | None = None,
    harness: AgentHarness = Depends(get_harness),
) -> ApproveResponse:
    state = harness.get_run(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    if state.action != "NEED_HUMAN_APPROVAL":
        raise HTTPException(status_code=409, detail=f"run does not require approval (action={state.action})")
    if state.approval_status != "PENDING":
        raise HTTPException(status_code=409, detail=f"run already {state.approval_status}")

    approved = body.approved if body is not None else True
    state.approval_status = "APPROVED" if approved else "REJECTED"
    return ApproveResponse(run_id=run_id, approval_status=state.approval_status)
