from __future__ import annotations

from sentinel.domain.engines.prompt_validation.injection_detector import (
    InjectionDetector,
)
from sentinel.domain.engines.prompt_validation.pii_detector import PIIDetector
from sentinel.domain.engines.prompt_validation.policy_filter import PolicyFilter
from sentinel.domain.engines.prompt_validation.risk_scorer import RiskScorer
from sentinel.domain.models.decision import GuardrailDecision, PromptValidationResult
from sentinel.domain.models.pipeline_context import PipelineContext


def _overall_status(
    injection_status: str,
    pii_status: str,
    policy_status: str,
    risk_score: int,
) -> str:
    """Derive overall_status per business rules 4.1 / 4.5.

    R-PV-02 / R-PV-05: any block sub-check → BLOCK
    R-PV-06: risk_score ≥ 80 → BLOCK even without individual block flag
    R-PV-03 / R-PV-04: any flag (and no block) → FLAG
    R-PV-07: all pass → PASS
    """
    if injection_status == "block" or policy_status == "block":
        return "block"
    if risk_score >= 80:
        return "block"
    if injection_status == "flag" or pii_status == "flag":
        return "flag"
    return "pass"


class PromptValidationEngine:
    """Composes InjectionDetector, PIIDetector, PolicyFilter, and RiskScorer
    into a single pipeline stage.

    All sub-components are injected via constructor — no module-level singletons.
    """

    def __init__(
        self,
        injection_detector: InjectionDetector | None = None,
        pii_detector: PIIDetector | None = None,
        policy_filter: PolicyFilter | None = None,
        risk_scorer: RiskScorer | None = None,
    ) -> None:
        self._injection = injection_detector or InjectionDetector()
        self._pii = pii_detector or PIIDetector()
        self._policy = policy_filter or PolicyFilter()
        self._risk = risk_scorer or RiskScorer()

    def validate(self, context: PipelineContext) -> PipelineContext:
        """Run all prompt validation sub-checks and update *context* in-place.

        Mutates:
          - ``context.masked_prompt``    — if PII is detected
          - ``context.validation_result``
          - ``context.guardrail_decision`` — if overall_status == 'block'
          - ``context.is_terminal``      — True if blocked
          - ``context.retry_requested``  — cleared to False if blocked
        """
        prompt = context.masked_prompt  # use masked_prompt as canonical input

        # ── Sub-checks ────────────────────────────────────────────────────────
        injection_result = self._injection.check(prompt)
        pii_result = self._pii.check(prompt)
        policy_result = self._policy.check(prompt, context.policy)
        risk_score = self._risk.score(injection_result, pii_result, policy_result)

        # ── Apply PII masking to context ──────────────────────────────────────
        if pii_result.status == "flag":
            context.masked_prompt = pii_result.masked_text

        # ── Derive overall status ─────────────────────────────────────────────
        status = _overall_status(
            injection_result.status,
            pii_result.status,
            policy_result.status,
            risk_score,
        )

        # ── Assemble PromptValidationResult ───────────────────────────────────
        context.validation_result = PromptValidationResult.from_lists(
            injection_result=injection_result.status,
            injection_detail=injection_result.detail,
            pii_result=pii_result.status,
            pii_types=list(pii_result.pii_types),
            policy_result=policy_result.status,
            policy_violated_category=policy_result.violated_category,
            risk_score=risk_score,
            overall_status=status,  # type: ignore[arg-type]
        )

        # ── Terminal path: block ──────────────────────────────────────────────
        if status == "block":
            reason = _block_reason(
                injection_result.detail, policy_result.violated_category, risk_score
            )
            context.guardrail_decision = GuardrailDecision(
                decision_type="block",
                reason=reason,
                triggered_rule="PROMPT_VALIDATION_BLOCK",
                safety_filter_override=False,
            )
            context.mark_terminal()

        return context


# ── Helper ────────────────────────────────────────────────────────────────────


def _block_reason(
    injection_detail: str | None,
    violated_category: str | None,
    risk_score: int,
) -> str:
    if injection_detail:
        return f"Prompt injection detected: {injection_detail}"
    if violated_category:
        return f"Prompt violates restricted category: {violated_category}"
    return f"Aggregate risk score {risk_score} exceeds block threshold (80)"
