"""Regex/heuristic planner — no LLM call, deterministic.

Known limitation: only Arabic-numeral quantities (e.g. "3 個") are recognized.
Chinese numerals (e.g. "十個") are not parsed and fall through to a missing-
quantity ASK_CLARIFICATION. See docs/ARCHITECTURE.md.
"""

import re

from app.schemas.domain import PlannerOutput

_QUANTITY_PATTERN = re.compile(r"(\d+)\s*(?:個|台|臺|席次|seats?)")
_BUDGET_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:美元|美金|usd|dollars?)", re.IGNORECASE)
_FILLER_PATTERN = re.compile(
    "|".join(
        [
            r"請幫[^\d，,。]*?部",
            r"請幫我",
            r"幫我",
            r"請",
            r"採購",
            r"購買",
            r"買",
            r"下單",
            r"直接送出",
            r"直接下單",
            r"直接",
            r"建立請購並",
            r"送出",
            r"的採購單",
            r"的採購",
            r"各",
            r"總預算(?:控)?在",
            r"控在",
            r"以內",
        ]
    )
)
_PUNCTUATION_PATTERN = re.compile(r"[，,。.；;]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


class RuleBasedPlanner:
    def parse(self, department: str, raw_message: str) -> PlannerOutput:
        return PlannerOutput(
            department=department,
            raw_message=raw_message,
            item_query=self._extract_item_query(raw_message),
            quantity=self._extract_quantity(raw_message),
            budget_cap_usd=self._extract_budget_cap(raw_message),
        )

    def _extract_quantity(self, raw_message: str) -> int | None:
        match = _QUANTITY_PATTERN.search(raw_message)
        return int(match.group(1)) if match else None

    def _extract_budget_cap(self, raw_message: str) -> float | None:
        match = _BUDGET_PATTERN.search(raw_message)
        return float(match.group(1)) if match else None

    def _extract_item_query(self, raw_message: str) -> str | None:
        text = _QUANTITY_PATTERN.sub(" ", raw_message)
        text = _BUDGET_PATTERN.sub(" ", text)
        text = _FILLER_PATTERN.sub(" ", text)
        text = _PUNCTUATION_PATTERN.sub(" ", text)
        text = _WHITESPACE_PATTERN.sub(" ", text).strip()
        return text or None
