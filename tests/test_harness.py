"""End-to-end Agent Loop over the 11 canonical cases (5 official + 6 custom) in tests/data/requests.json."""

import json
from pathlib import Path

import pytest

from app.schemas.api import AgentRunRequest

_REQUESTS = json.loads(
    (Path(__file__).resolve().parent / "data" / "requests.json").read_text(encoding="utf-8")
)


def test_eleven_cases_are_present(requests_data):
    assert len(requests_data) == 11
    assert {c["source"] for c in requests_data} == {"official", "custom"}


@pytest.mark.parametrize("case", _REQUESTS, ids=[c["id"] for c in _REQUESTS])
def test_case_matches_expected_behavior(harness, case):
    request = AgentRunRequest(user_id=case["user_id"], department=case["department"], message=case["message"])

    response = harness.run(request)

    assert response.decision.action == case["expected_behavior"], case


def test_create_draft_po_case_has_draft_and_completed_status(harness, requests_data):
    case = next(c for c in requests_data if c["id"] == "case_001")
    request = AgentRunRequest(user_id=case["user_id"], department=case["department"], message=case["message"])

    response = harness.run(request)

    assert response.status == "COMPLETED"
    assert response.draft_po is not None
    assert response.decision.requires_human_approval is False


def test_need_human_approval_case_has_no_draft_and_awaiting_status(harness, requests_data):
    case = next(c for c in requests_data if c["id"] == "custom_005")
    request = AgentRunRequest(user_id=case["user_id"], department=case["department"], message=case["message"])

    response = harness.run(request)

    assert response.status == "AWAITING_APPROVAL"
    assert response.draft_po is None
    assert response.decision.requires_human_approval is True


def test_reject_case_has_no_draft(harness, requests_data):
    case = next(c for c in requests_data if c["id"] == "case_005")
    request = AgentRunRequest(user_id=case["user_id"], department=case["department"], message=case["message"])

    response = harness.run(request)

    assert response.status == "COMPLETED"
    assert response.draft_po is None
    assert response.decision.action == "REJECT"
