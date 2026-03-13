"""Unit tests for GuardrailDecisionEngine.

Verifies the 6-rule priority ordering that is the correctness invariant
for the entire pipeline decision path.
"""
from __future__ import annotations

import pytest

from sentinel.domain.engines.decision_engine import GuardrailDecisionEngine
from sentinel.domain.models.confidence import ConfidenceScore
from sentinel.domain.models.decision import (
    PromptValidationResult,
    SafetyFilterResult,
)
from sentinel.domain.models.pipeline_context import PipelineContext
from sentinel.domain.models.policy import PolicySnapshot


# ── Helpers ───────────────────────────────────────────────────────────────────


def _policy(
    accept: int = 70,
    warn: int = 40,
    block: int = 0,
    max_retries: int = 2,
    fallback_priority: list[str] | None = None,
) -> PolicySnapshot:
    return PolicySnapshot(
        accept_threshold=accept,
        warn_threshold=warn,
        block_threshold=block,
        max_retries=max_retries,
        fallback_priority=fallback_priority
        or ["retry_prompt", "retry_lower_temp", "rag_augmentation", "alternate_model"],
    )


def _ctx(
    score: int = 75,
    policy: PolicySnapshot | None = None,
    safety_results: list[SafetyFilterResult] | None = None,
    validation_overall_status: str | None = None,
    attempt_number: int = 1,
    kb_id: str | None = None,
) -> PipelineContext:
    pol = policy or _policy()
    ctx = PipelineContext(
        request_id="req-test",
        session_id="sess-test",
        original_prompt="test",
        masked_prompt="test",
        model_provider="ollama",
        model_name="llama3",
        kb_id=kb_id,
        policy=pol,
    )
    ctx.attempt_number = attempt_number
    ctx.confidence_score = ConfidenceScore.from_dict(
        value=score,
        label="high" if score >= pol.accept_threshold else "medium" if score >= pol.warn_threshold else "low",
        signal_breakdown={"evidence_similarity": 0.5, "claim_verification_ratio": 0.5,
                          "claim_density_penalty": 1.0, "safety_penalty": 1.0},
    )
    if safety_results is not None:
        ctx.safety_results = safety_results
    if validation_overall_status:
        ctx.validation_result = PromptValidationResult.from_lists(
            injection_result="block" if validation_overall_status == "block" else "pass",
            injection_detail="injection detected" if validation_overall_status == "block" else None,
            pii_result="pass",
            pii_types=[],
            policy_result="pass",
            policy_violated_category=None,
            risk_score=90 if validation_overall_status == "block" else 0,
            overall_status=validation_overall_status,  # type: ignore[arg-type]
        )
    return ctx


def _safety(name: str, score: float) -> SafetyFilterResult:
    return SafetyFilterResult(
        filter_name=name,
        result="flagged",
        score=score,
    )


@pytest.fixture(scope="module")
def engine() -> GuardrailDecisionEngine:
    return GuardrailDecisionEngine()


# ── Rule 1: Safety filter override ───────────────────────────────────────────


class TestSafetyOverride:
    def test_safety_score_08_blocks_regardless_of_confidence_90(
        self, engine: GuardrailDecisionEngine
    ) -> None:
        ctx = _ctx(score=90, safety_results=[_safety("toxicity", 0.8)])
        engine.decide(ctx)
        assert ctx.guardrail_decision is not None
        assert ctx.guardrail_decision.decision_type == "block"
        assert ctx.guardrail_decision.safety_filter_override is True
        assert ctx.is_terminal is True

    def test_safety_score_07_is_boundary_block(self, engine: GuardrailDecisionEngine) -> None:
        ctx = _ctx(score=95, safety_results=[_safety("hate_speech", 0.7)])
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "block"
        assert ctx.guardrail_decision.safety_filter_override is True

    def test_safety_score_069_does_not_override(self, engine: GuardrailDecisionEngine) -> None:
        ctx = _ctx(score=80, safety_results=[_safety("toxicity", 0.69)])
        engine.decide(ctx)
        # Low-confidence safety flag: falls through to confidence-based decision
        assert ctx.guardrail_decision is not None
        assert ctx.guardrail_decision.decision_type != "block" or ctx.guardrail_decision.safety_filter_override is False

    def test_safety_override_sets_is_terminal(self, engine: GuardrailDecisionEngine) -> None:
        ctx = _ctx(score=99, safety_results=[_safety("harmful", 0.95)])
        engine.decide(ctx)
        assert ctx.is_terminal is True
        assert ctx.retry_requested is False

    def test_safety_filter_override_false_on_non_safety_block(
        self, engine: GuardrailDecisionEngine
    ) -> None:
        ctx = _ctx(score=0)
        engine.decide(ctx)
        assert ctx.guardrail_decision is not None
        assert ctx.guardrail_decision.safety_filter_override is False


# ── Rule 2: Prompt validation block (defensive) ───────────────────────────────


class TestPromptValidationBlock:
    def test_validation_block_produces_block_decision(
        self, engine: GuardrailDecisionEngine
    ) -> None:
        ctx = _ctx(score=75, validation_overall_status="block")
        engine.decide(ctx)
        assert ctx.guardrail_decision is not None
        assert ctx.guardrail_decision.decision_type == "block"
        assert ctx.guardrail_decision.triggered_rule == "PROMPT_VALIDATION_BLOCK"
        assert ctx.is_terminal is True

    def test_validation_block_safety_override_is_false(
        self, engine: GuardrailDecisionEngine
    ) -> None:
        ctx = _ctx(score=80, validation_overall_status="block")
        engine.decide(ctx)
        assert ctx.guardrail_decision.safety_filter_override is False


# ── Rule 3: Accept ────────────────────────────────────────────────────────────


class TestAccept:
    def test_score_at_accept_threshold_accepts(self, engine: GuardrailDecisionEngine) -> None:
        ctx = _ctx(score=70)  # == accept_threshold
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "accept"
        assert ctx.is_terminal is False
        assert ctx.retry_requested is False

    def test_score_above_accept_threshold_accepts(
        self, engine: GuardrailDecisionEngine
    ) -> None:
        ctx = _ctx(score=95)
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "accept"

    def test_accept_does_not_set_terminal(self, engine: GuardrailDecisionEngine) -> None:
        ctx = _ctx(score=80)
        engine.decide(ctx)
        assert ctx.is_terminal is False


# ── Rule 4: Accept with warning ───────────────────────────────────────────────


class TestAcceptWithWarning:
    def test_score_at_warn_threshold_warns(self, engine: GuardrailDecisionEngine) -> None:
        ctx = _ctx(score=40)  # == warn_threshold
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "accept_with_warning"
        assert ctx.guardrail_decision.triggered_rule == "CONFIDENCE_WARN_THRESHOLD"

    def test_score_just_below_accept_warns(self, engine: GuardrailDecisionEngine) -> None:
        ctx = _ctx(score=69)  # accept=70 → warn
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "accept_with_warning"

    def test_low_confidence_safety_flag_warns(self, engine: GuardrailDecisionEngine) -> None:
        # safety score 0.5 < 0.7 → no block; score 75 ≥ accept → but flagged_safety
        # forces accept_with_warning path in Rule 3 (flagged_safety excludes Rule 3)
        ctx = _ctx(score=75, safety_results=[_safety("mild_toxicity", 0.5)])
        engine.decide(ctx)
        # With flagged_safety present, Rule 3 is skipped even at score≥accept_threshold
        assert ctx.guardrail_decision.decision_type == "accept_with_warning"
        assert ctx.guardrail_decision.safety_filter_override is True


# ── Rule 5: Retry dispatch ────────────────────────────────────────────────────


class TestRetryDispatch:
    def test_low_score_triggers_retry(self, engine: GuardrailDecisionEngine) -> None:
        ctx = _ctx(score=20, attempt_number=1)
        engine.decide(ctx)
        assert ctx.guardrail_decision is not None
        assert ctx.retry_requested is True
        assert ctx.is_terminal is False

    def test_first_fallback_strategy_selected(self, engine: GuardrailDecisionEngine) -> None:
        pol = _policy(fallback_priority=["retry_prompt", "retry_lower_temp"])
        ctx = _ctx(score=20, policy=pol, attempt_number=1)
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "retry_prompt"
        assert ctx.guardrail_decision.triggered_rule == "CONFIDENCE_RETRY_THRESHOLD"

    def test_already_tried_first_strategy_uses_second(
        self, engine: GuardrailDecisionEngine
    ) -> None:
        pol = _policy(fallback_priority=["retry_prompt", "retry_lower_temp"])
        ctx = _ctx(score=20, policy=pol, attempt_number=2)
        ctx.stage_start_times["_attempted:retry_prompt"] = 1.0
        engine.decide(ctx)
        # retry_lower_temp maps to decision_type="retry_prompt" per arch spec
        assert ctx.retry_requested is True

    def test_rag_skipped_when_no_kb(self, engine: GuardrailDecisionEngine) -> None:
        pol = _policy(fallback_priority=["rag_augmentation", "retry_prompt"])
        ctx = _ctx(score=20, policy=pol, attempt_number=1, kb_id=None)
        engine.decide(ctx)
        # rag skipped, falls to retry_prompt
        assert ctx.guardrail_decision.decision_type == "retry_prompt"


# ── Retry budget exhausted → block ───────────────────────────────────────────


class TestRetryBudgetExhausted:
    def test_all_strategies_attempted_blocks(self, engine: GuardrailDecisionEngine) -> None:
        pol = _policy(max_retries=2, fallback_priority=["retry_prompt", "retry_lower_temp"])
        ctx = _ctx(score=20, policy=pol, attempt_number=3)
        # Mark both strategies attempted
        ctx.stage_start_times["_attempted:retry_prompt"] = 1.0
        ctx.stage_start_times["_attempted:retry_lower_temp"] = 1.0
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "block"
        assert ctx.is_terminal is True
        assert ctx.retry_requested is False

    def test_max_retries_exceeded_blocks(self, engine: GuardrailDecisionEngine) -> None:
        pol = _policy(max_retries=1)
        ctx = _ctx(score=20, policy=pol, attempt_number=2)
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "block"
        assert ctx.is_terminal is True
        assert "retries" in ctx.guardrail_decision.reason.lower()


# ── Rule 6: Absolute block (score < block_threshold) ─────────────────────────


class TestAbsoluteBlock:
    def test_score_below_block_threshold_blocks(self, engine: GuardrailDecisionEngine) -> None:
        pol = _policy(accept=70, warn=40, block=20)
        ctx = _ctx(score=10, policy=pol)
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "block"
        assert ctx.guardrail_decision.triggered_rule == "CONFIDENCE_ABSOLUTE_BLOCK"
        assert ctx.is_terminal is True


# ── Priority ordering invariant ───────────────────────────────────────────────


class TestPriorityInvariant:
    def test_safety_overrides_confidence_100(self, engine: GuardrailDecisionEngine) -> None:
        """Rule 1 must beat confidence=100 (correctness invariant)."""
        ctx = _ctx(score=100, safety_results=[_safety("toxicity", 0.95)])
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "block"
        assert ctx.guardrail_decision.safety_filter_override is True

    def test_safety_overrides_validation_pass(self, engine: GuardrailDecisionEngine) -> None:
        ctx = _ctx(score=85, safety_results=[_safety("hate", 0.8)],
                   validation_overall_status=None)
        engine.decide(ctx)
        assert ctx.guardrail_decision.safety_filter_override is True

    def test_validation_block_overrides_high_confidence(
        self, engine: GuardrailDecisionEngine
    ) -> None:
        """Rule 2 must fire even when confidence is high."""
        ctx = _ctx(score=95, validation_overall_status="block")
        engine.decide(ctx)
        assert ctx.guardrail_decision.triggered_rule == "PROMPT_VALIDATION_BLOCK"


class TestDecisionEngineGuards:
    def test_raises_if_confidence_score_none(self, engine: GuardrailDecisionEngine) -> None:
        """decide() must raise ValueError if confidence_score has not been set."""
        from sentinel.domain.models.policy import PolicySnapshot
        ctx = PipelineContext(
            request_id="r",
            session_id="s",
            original_prompt="p",
            masked_prompt="p",
            model_provider="ollama",
            model_name="llama3",
            kb_id=None,
            policy=PolicySnapshot(),
        )
        # confidence_score is None by default
        with pytest.raises(ValueError, match="confidence_score"):
            engine.decide(ctx)

    def test_no_fallback_strategies_exhausted_is_terminal(
        self, engine: GuardrailDecisionEngine
    ) -> None:
        """When all 4 strategies are pre-attempted, retry budget is gone → block."""
        pol = _policy(
            accept=70, warn=40, block=0, max_retries=4,
            fallback_priority=["retry_prompt", "retry_lower_temp", "rag_augmentation", "alternate_model"],
        )
        ctx = _ctx(score=20, policy=pol, attempt_number=1)
        # Mark all strategies as attempted
        for s in ["retry_prompt", "retry_lower_temp", "rag_augmentation", "alternate_model"]:
            ctx.stage_start_times[f"_attempted:{s}"] = 1.0
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "block"
        assert ctx.is_terminal is True

    def test_rag_strategy_used_when_kb_present(self, engine: GuardrailDecisionEngine) -> None:
        pol = _policy(fallback_priority=["rag_augmentation", "retry_prompt"])
        ctx = _ctx(score=20, policy=pol, attempt_number=1, kb_id="kb-abc")
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "trigger_rag"

    def test_warn_threshold_boundary_exact(self, engine: GuardrailDecisionEngine) -> None:
        """score == warn_threshold exactly → accept_with_warning, not retry."""
        ctx = _ctx(score=40)  # == warn_threshold default
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "accept_with_warning"

    def test_accept_threshold_boundary_exact(self, engine: GuardrailDecisionEngine) -> None:
        """score == accept_threshold exactly → accept (no safety flags)."""
        ctx = _ctx(score=70)  # == accept_threshold default
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "accept"

    def test_validation_block_reason_includes_detail(
        self, engine: GuardrailDecisionEngine
    ) -> None:
        ctx = _ctx(score=80, validation_overall_status="block")
        engine.decide(ctx)
        assert "injection detected" in ctx.guardrail_decision.reason.lower()

    def test_validation_result_pass_does_not_block(
        self, engine: GuardrailDecisionEngine
    ) -> None:
        """validation_result with overall_status='pass' must NOT trigger Rule 2."""
        ctx = _ctx(score=80)
        from sentinel.domain.models.decision import PromptValidationResult
        ctx.validation_result = PromptValidationResult.from_lists(
            injection_result="pass",
            injection_detail=None,
            pii_result="pass",
            pii_types=[],
            policy_result="pass",
            policy_violated_category=None,
            risk_score=5,
            overall_status="pass",
        )
        engine.decide(ctx)
        assert ctx.guardrail_decision.decision_type == "accept"
