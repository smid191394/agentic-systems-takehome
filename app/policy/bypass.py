"""policy_004 — layered bypass/prompt-injection detection.

Layer A (pattern) runs first and is cheap/deterministic: a hit short-circuits
straight to REJECT without ever calling the classifier. Only when Layer A
misses does Layer B (semantic classifier) run, to catch paraphrased bypass
attempts that don't contain a literal keyword. The classifier only ever emits
a `suspicious` signal — BypassGate is the sole place that turns any of this
into an action.

Layer B is RuleBasedBypassClassifier: a deterministic soft-keyword heuristic
behind the `BypassClassifierClient` Protocol. A real LLM-backed classifier
could implement the same Protocol and drop in without changing BypassGate
or ToolRegistry — the Protocol is what makes Layer B swappable, not a
pre-existing stub.

Fail-closed: any Layer B failure (no client configured, classifier raises) is
treated the same as "could not verify" -> NEED_HUMAN_APPROVAL, never
auto-execute. This is a deliberate reversal of "fail open on error".
"""

from typing import Protocol

from app.schemas.domain import BypassAssessment, BypassEvaluation, BypassLLMResult

BYPASS_PATTERNS = [
    "忽略",
    "跳過",
    "不需核准",
    "不要核准",
    "直接送出",
    "直接下單",
    "ignore policy",
    "bypass",
    "skip approval",
]


def pattern_hit(raw_message: str) -> bool:
    lowered = raw_message.lower()
    return any(pattern.lower() in lowered for pattern in BYPASS_PATTERNS)


class BypassClassifierClient(Protocol):
    def classify(self, raw_message: str) -> BypassLLMResult: ...


class RuleBasedBypassClassifier:
    """Deterministic stand-in for a semantic classifier — no LLM call.

    Looks for softer/paraphrased bypass language that Layer A's literal
    keyword scan deliberately misses (e.g. "省略審核流程", "不用走核准"),
    while trying not to flag messages that merely *mention* the approval
    process without asking to skip it (e.g. "已經過審核流程確認需求").
    """

    SOFT_BYPASS_SIGNALS = [
        "省略審核",
        "省略核准",
        "免審核",
        "免核准",
        "不用走核准",
        "不用核准",
        "不用審核",
        "跳過流程",
        "跳過審核",
        "越過審核",
        "口頭同意",
        "先做後補",
        "事後補簽",
        "事後補",
    ]

    def classify(self, raw_message: str) -> BypassLLMResult:
        hit = next((signal for signal in self.SOFT_BYPASS_SIGNALS if signal in raw_message), None)
        if hit is not None:
            return BypassLLMResult(
                suspicious=True,
                reason=f"message contains a soft bypass signal: '{hit}'",
                confidence=0.7,
            )
        return BypassLLMResult(suspicious=False, reason="no bypass signal detected", confidence=0.9)


class BypassEvaluator:
    def __init__(self, client: BypassClassifierClient | None) -> None:
        self._client = client

    def evaluate(self, raw_message: str) -> BypassAssessment:
        if pattern_hit(raw_message):
            return BypassAssessment(pattern_hit=True, llm_called=False, llm_skipped_reason="pattern_hit")

        if self._client is None:
            return BypassAssessment(
                pattern_hit=False,
                llm_called=True,
                llm_error="no bypass classifier client configured",
            )

        try:
            result = self._client.classify(raw_message)
        except Exception as exc:
            # Broad on purpose: this is the fail-closed security boundary. Any
            # classifier failure (timeout, malformed output, bug) must fail
            # closed here rather than propagate into a 500 that skips
            # PolicyEngine's decision entirely.
            return BypassAssessment(pattern_hit=False, llm_called=True, llm_error=str(exc))

        return BypassAssessment(pattern_hit=False, llm_called=True, llm=result)


class BypassGate:
    """Harness step 2 (right after RunState init) — the sole place that turns a
    BypassAssessment into an action. Runs before the Planner even sees the
    message: a REJECT/NEED_HUMAN_APPROVAL verdict here short-circuits the run
    without spending Planner/catalog/policy work on a message that's already
    been decided.

    `action="PASS"` means both layers cleared — the run should continue
    normally into Planner.parse and the rest of the loop.
    """

    def __init__(self, evaluator: BypassEvaluator) -> None:
        self._evaluator = evaluator

    def check(self, raw_message: str) -> BypassEvaluation:
        assessment = self._evaluator.evaluate(raw_message)

        if assessment.pattern_hit:
            return BypassEvaluation(
                action="REJECT", reasons=["bypass_pattern_detected"], assessment=assessment
            )

        if assessment.llm is not None and assessment.llm.suspicious:
            return BypassEvaluation(
                action="NEED_HUMAN_APPROVAL", reasons=["bypass_llm_suspicious"], assessment=assessment
            )

        if assessment.llm is None and assessment.llm_error is not None:
            return BypassEvaluation(
                action="NEED_HUMAN_APPROVAL", reasons=["bypass_llm_unavailable"], assessment=assessment
            )

        return BypassEvaluation(action="PASS", reasons=[], assessment=assessment)
