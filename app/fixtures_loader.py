"""Loads catalog/policies/budgets fixtures once at startup."""

import json
from pathlib import Path

from pydantic import BaseModel

from app.schemas.domain import CatalogItem, DepartmentBudget, PoliciesConfig


class Fixtures(BaseModel):
    catalog: list[CatalogItem]
    policies: PoliciesConfig
    budgets: dict[str, DepartmentBudget]


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_fixtures(fixtures_dir: Path) -> Fixtures:
    catalog_data = _read_json(fixtures_dir / "catalog.json")
    policies_data = _read_json(fixtures_dir / "policies.json")
    budgets_data = _read_json(fixtures_dir / "budgets.json")

    return Fixtures(
        catalog=[CatalogItem.model_validate(item) for item in catalog_data],
        policies=PoliciesConfig.model_validate(policies_data),
        budgets={
            department: DepartmentBudget.model_validate(budget) for department, budget in budgets_data.items()
        },
    )
