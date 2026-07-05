"""create_draft_po — only reachable once PolicyEngine has returned CREATE_DRAFT_PO."""

from app.schemas.api import DraftPO
from app.schemas.domain import CatalogItem


def create_draft_po(*, item: CatalogItem, quantity: int, department: str) -> DraftPO:
    return DraftPO(
        item=item.name,
        quantity=quantity,
        estimated_total=quantity * item.unit_price,
        department=department,
    )
