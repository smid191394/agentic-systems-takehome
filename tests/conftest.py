"""Shared fixtures: fixtures/*.json loaders and a real (non-mocked) harness stack."""

import json
from pathlib import Path

import pytest

from app.fixtures_loader import Fixtures, load_fixtures
from app.harness.runner import AgentHarness
from app.planner.rule_based import RuleBasedPlanner
from app.policy.bypass import BypassEvaluator, RuleBasedBypassClassifier
from app.policy.engine import PolicyEngine
from app.tools.registry import ToolRegistry

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
TEST_DATA_DIR = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="session")
def fixtures() -> Fixtures:
    return load_fixtures(FIXTURES_DIR)


@pytest.fixture
def policy_engine(fixtures: Fixtures) -> PolicyEngine:
    bypass_evaluator = BypassEvaluator(RuleBasedBypassClassifier())
    return PolicyEngine(fixtures.policies, fixtures.budgets, bypass_evaluator)


@pytest.fixture
def tool_registry(fixtures: Fixtures, policy_engine: PolicyEngine) -> ToolRegistry:
    return ToolRegistry(fixtures.catalog, policy_engine)


@pytest.fixture
def harness(fixtures: Fixtures, tool_registry: ToolRegistry) -> AgentHarness:
    return AgentHarness(RuleBasedPlanner(), fixtures.catalog, tool_registry)


@pytest.fixture(scope="session")
def requests_data() -> list[dict]:
    return json.loads((TEST_DATA_DIR / "requests.json").read_text(encoding="utf-8"))
