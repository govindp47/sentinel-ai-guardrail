from __future__ import annotations

from sentinel.domain.models.decision import GuardrailDecision
from sentinel.domain.models.pipeline_context import PipelineContext

# ── Strategy → GuardrailDecision.decision_type mapping ────────────────────────

_STRATEGY_TO_DECISION_TYPE: dict[str, str] = {
    "retry_prompt": "retry_prompt",
    "retry_lower_temp": "retry_prompt",
    "rag_augmentation": "trigger_rag",
    "alternate_model": "retry_alternate_model",
}


class GuardrailDecisionEngine:
    """Pure synchronous decision engine — no I/O, no side effects.

    Implements the priority-ordered decision rules from
    04_DOMAIN_ENGINE_DESIGN.md section 8.1 exactly:

        Rule 1  Safety filter override (score ≥ 0.7) → BLOCK
        Rule 2  Prompt validation block (defensive)  → BLOCK
        Rule 3  Confidence ≥ accept_threshold         → ACCEPT
        Rule 4  Confidence ≥ warn_threshold           → ACCEPT_WITH_WARNING
        Rule 5  Confidence ≥ block_threshold + retry budget → RETRY
        Rule 6  Confidence < block_threshold          → BLOCK
    """

    def decide(self, context: PipelineContext) -> PipelineContext:
        """Evaluate all signals and set ``context.guardrail_decision``.

        Invariants guaranteed:
        - ``is_terminal = True`` on every block decision.
        - ``retry_requested = True`` on every retry decision.
        - ``safety_filter_override = True`` only when Rule 1 fires.
        """
        if context.confidence_score is None:
            raise ValueError(
                "GuardrailDecisionEngine.decide() requires context.confidence_score "
                "to be set. Run ConfidenceScoringEngine.compute() first."
            )

        policy = context.policy
        score = context.confidence_score.value
        flagged_safety = [r for r in context.safety_results if r.result == "flagged"]

        # ── Rule 1: Safety filter override ───────────────────────────────────
        if flagged_safety:
            most_severe = max(flagged_safety, key=lambda r: r.score)
            if most_severe.score >= 0.7:
                context.guardrail_decision = GuardrailDecision(
                    decision_type="block",
                    reason=f"Safety filter triggered: {most_severe.filter_name}",
                    triggered_rule="SAFETY_FILTER_BLOCK",
                    safety_filter_override=True,
                )
                context.is_terminal = True
                context.retry_requested = False
                return context
            # Low-confidence safety flag: falls through to confidence-based decision

        # ── Rule 2: Prompt validation block (defensive) ───────────────────────
        if (
            context.validation_result is not None
            and context.validation_result.overall_status == "block"
        ):
            detail = (
                context.validation_result.injection_detail
                or context.validation_result.policy_violated_category
                or "prompt validation failed"
            )
            context.guardrail_decision = GuardrailDecision(
                decision_type="block",
                reason=f"Prompt blocked at validation: {detail}",
                triggered_rule="PROMPT_VALIDATION_BLOCK",
                safety_filter_override=False,
            )
            context.is_terminal = True
            context.retry_requested = False
            return context

        # ── Rule 3: Accept ────────────────────────────────────────────────────
        if score >= policy.accept_threshold and not flagged_safety:
            context.guardrail_decision = GuardrailDecision(
                decision_type="accept",
                reason=(
                    f"Confidence score {score} meets accept threshold " f"{policy.accept_threshold}"
                ),
                triggered_rule=None,
                safety_filter_override=False,
            )
            return context

        # ── Rule 4: Accept with warning ───────────────────────────────────────
        if score >= policy.warn_threshold:
            safety_prefix = (
                f"Safety filter low-confidence flag: {flagged_safety[0].filter_name}. "
                if flagged_safety
                else ""
            )
            context.guardrail_decision = GuardrailDecision(
                decision_type="accept_with_warning",
                reason=(
                    f"{safety_prefix}Confidence score {score} is in warn range "
                    f"[{policy.warn_threshold}, {policy.accept_threshold})"
                ),
                triggered_rule="CONFIDENCE_WARN_THRESHOLD",
                safety_filter_override=bool(flagged_safety),
            )
            return context

        # ── Rule 5: Retry (confidence in fallback range) ──────────────────────
        if score >= policy.block_threshold:
            next_strategy = self._select_fallback_strategy(context)
            if next_strategy is not None and context.attempt_number <= policy.max_retries:
                decision_type = _STRATEGY_TO_DECISION_TYPE.get(next_strategy, "retry_prompt")
                context.guardrail_decision = GuardrailDecision(
                    decision_type=decision_type,  # type: ignore[arg-type]
                    reason=(
                        f"Confidence score {score} below warn threshold "
                        f"{policy.warn_threshold}; attempting fallback: {next_strategy}"
                    ),
                    triggered_rule="CONFIDENCE_RETRY_THRESHOLD",
                    safety_filter_override=False,
                )
                context.retry_requested = True
                return context

            # No strategies left or retry budget exhausted
            context.guardrail_decision = GuardrailDecision(
                decision_type="block",
                reason=(
                    "Maximum retries exceeded"
                    if context.attempt_number > policy.max_retries
                    else (
                        f"Confidence score {score} below threshold; "
                        "no further fallback strategies available"
                    )
                ),
                triggered_rule="MAX_RETRIES_EXCEEDED"
                if context.attempt_number > policy.max_retries
                else "CONFIDENCE_BLOCK_THRESHOLD",
                safety_filter_override=False,
            )
            context.is_terminal = True
            context.retry_requested = False
            return context

        # ── Rule 6: Block (score < block_threshold) ────────────────────────────
        context.guardrail_decision = GuardrailDecision(
            decision_type="block",
            reason=(f"Confidence score {score} below block threshold " f"{policy.block_threshold}"),
            triggered_rule="CONFIDENCE_ABSOLUTE_BLOCK",
            safety_filter_override=False,
        )
        context.is_terminal = True
        context.retry_requested = False
        return context

    # ── Private helpers ───────────────────────────────────────────────────────

    def _select_fallback_strategy(self, context: PipelineContext) -> str | None:
        """Return the first un-attempted strategy from policy.fallback_priority.

        Attempted strategies are tracked in ``context.stage_start_times``
        using sentinel keys of the form ``"_attempted:<strategy>"``.
        RAG augmentation is skipped when no KB is active.
        """
        for strategy in context.policy.fallback_priority:
            if strategy == "rag_augmentation" and not context.kb_id:
                continue
            if context.stage_start_times.get(f"_attempted:{strategy}") is None:
                return strategy
        return None
