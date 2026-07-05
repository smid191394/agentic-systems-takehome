"""lookup_catalog — the only place catalog knowledge (aliases, categories) lives.

Scans both raw_message and item_query for name/alias substrings so that a
message mentioning two distinct items (e.g. "Figma 跟 MacBook Pro") is treated
the same as a lexically ambiguous alias: multiple matches -> "ambiguous" ->
the harness asks for clarification either way.
"""

from app.schemas.domain import CatalogItem, LookupCatalogOutput


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def lookup_catalog(
    *,
    item_query: str,
    raw_message: str,
    catalog_items: list[CatalogItem],
) -> LookupCatalogOutput:
    haystacks = [raw_message, item_query]
    matched_ids: list[str] = []

    for item in catalog_items:
        candidates = [item.name, *item.aliases]
        if any(_contains(haystack, candidate) for haystack in haystacks for candidate in candidates):
            matched_ids.append(item.id)

    if not matched_ids:
        return LookupCatalogOutput(result="not_found")

    if len(matched_ids) > 1:
        return LookupCatalogOutput(result="ambiguous", matched_item_ids=matched_ids)

    item = next(i for i in catalog_items if i.id == matched_ids[0])
    return LookupCatalogOutput(
        result="found",
        item_id=item.id,
        name=item.name,
        unit_price=item.unit_price,
        category=item.category,
    )
