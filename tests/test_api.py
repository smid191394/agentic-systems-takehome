"""HTTP-level spot checks — request/response schema validation is FastAPI's job; this just checks wiring."""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_case_001_create_draft_po(client: TestClient):
    response = client.post(
        "/agent/run",
        json={
            "user_id": "u_001",
            "department": "marketing",
            "message": "請幫行銷部採購 3 個 Figma Enterprise 席次，總預算在 3000 美元以內。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["action"] == "CREATE_DRAFT_PO"
    assert body["status"] == "COMPLETED"
    assert body["draft_po"] is not None


def test_missing_required_field_returns_422(client: TestClient):
    response = client.post("/agent/run", json={"user_id": "u_001", "message": "缺少 department"})

    assert response.status_code == 422


def test_unknown_department_returns_200_not_422(client: TestClient):
    response = client.post(
        "/agent/run",
        json={
            "user_id": "u_custom_007",
            "department": "sales",
            "message": "請幫業務部採購 2 個 Figma Enterprise Seat。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["action"] == "NEED_HUMAN_APPROVAL"
    assert body["status"] == "AWAITING_APPROVAL"


def test_run_not_found_returns_404(client: TestClient):
    response = client.post("/agent/runs/does-not-exist/approve")

    assert response.status_code == 404
