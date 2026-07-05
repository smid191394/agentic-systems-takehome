"""lookup_catalog — the only place with alias/ambiguity/multi-item logic worth its own test file."""

from app.schemas.domain import CatalogItem
from app.tools.catalog import lookup_catalog

CATALOG = [
    {
        "id": "item_figma_enterprise",
        "name": "Figma Enterprise Seat",
        "aliases": ["figma", "figma enterprise", "figma seat"],
        "unit_price": 800,
        "category": "software",
    },
    {
        "id": "item_macbook_pro",
        "name": "MacBook Pro",
        "aliases": ["macbook", "macbook pro", "laptop"],
        "unit_price": 2500,
        "category": "hardware",
    },
]


def _items():
    return [CatalogItem.model_validate(item) for item in CATALOG]


def test_found_by_exact_name():
    result = lookup_catalog(
        item_query="MacBook Pro", raw_message="請幫我買 MacBook Pro", catalog_items=_items()
    )

    assert result.result == "found"
    assert result.item_id == "item_macbook_pro"
    assert result.unit_price == 2500
    assert result.category == "hardware"


def test_found_by_alias_case_insensitive():
    result = lookup_catalog(item_query="FIGMA", raw_message="請幫我買 FIGMA", catalog_items=_items())

    assert result.result == "found"
    assert result.item_id == "item_figma_enterprise"


def test_not_found_for_unknown_item():
    result = lookup_catalog(item_query="asdfghjkl", raw_message="請幫我買 asdfghjkl", catalog_items=_items())

    assert result.result == "not_found"
    assert result.item_id is None


def test_ambiguous_when_raw_message_mentions_two_items():
    result = lookup_catalog(
        item_query="Figma 跟 MacBook Pro",
        raw_message="請幫我買 Figma 跟 MacBook Pro 各一個",
        catalog_items=_items(),
    )

    assert result.result == "ambiguous"
    assert set(result.matched_item_ids) == {"item_figma_enterprise", "item_macbook_pro"}


def test_match_via_raw_message_even_when_item_query_differs():
    result = lookup_catalog(item_query="", raw_message="請幫我買 laptop 一台", catalog_items=_items())

    assert result.result == "found"
    assert result.item_id == "item_macbook_pro"
