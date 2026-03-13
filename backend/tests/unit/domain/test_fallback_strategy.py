"""Unit tests for FallbackStrategyEngine — one test per strategy type."""
from __future__ import annotations

import pytest

from sentinel.domain.engines.fallback_strategy import (
    FallbackStrategyEngine,
    _STRICTER_PROMPT_SUFFIX,
    _DEFAULT_ALTERNATE_MODEL,
    _DEFAULT_ALTERNATE_PROVIDER,
)
from sentinel.domain.models.confidence import ConfidenceScore
from sentinel.domain.models.decision import GuardrailDecision
from sentinel.domain.models.pipeline_context import PipelineContext
from sentinel.domain.models.policy import PolicySnapshot


# ── Helpers ───────────────────────────────────────────────────────────────────


def _ctx(
    masked_prompt: str = "original prompt",
    model_provider: str = "ollama",
    model_name: str = "llama3",
    kb_id: str | None = None,
) -> PipelineContext:
    ctx = PipelineContext(
        request_id="req-test",
        session_id="sess-test",
        original_prompt=masked_prompt,
        masked_prompt=masked_prompt,
        model_provider=model_provider,
        model_name=model_name,
        kb_id=kb_id,
        policy=PolicySnapshot(),
    )
    # Pre-populate some stage outputs to verify they're cleared
    ctx.llm_response_text = "some LLM response"
    ctx.guardrail_decision = GuardrailDecision(
        decision_type="retry_prompt",
        reason="test",
        triggered_rule=None,
        safety_filter_override=False,
    )
    ctx.confidence_score = ConfidenceScore.from_dict(
        value=50, label="medium", signal_breakdown={}
    )
    return ctx


@pytest.fixture(scope="module")
def engine() -> FallbackStrategyEngine:
    return FallbackStrategyEngine()


# ── Strategy: retry_prompt ────────────────────────────────────────────────────


class TestRetryPromptStrategy:
    def test_appends_suffix_to_masked_prompt(self, engine: FallbackStrategyEngine) -> None:
        ctx = _ctx(masked_prompt="What is the capital?")
        engine.apply(ctx, "retry_prompt")
        assert ctx.masked_prompt == "What is the capital?" + _STRICTER_PROMPT_SUFFIX

    def test_sets_fallback_strategy_applied(self, engine: FallbackStrategyEngine) -> None:
        ctx = _ctx()
        engine.apply(ctx, "retry_prompt")
        assert ctx.fallback_strategy_applied == "retry_prompt"

    def test_marks_strategy_attempted(self, engine: FallbackStrategyEngine) -> None:
        ctx = _ctx()
        engine.apply(ctx, "retry_prompt")
        assert ctx.stage_start_times.get("_attempted:retry_prompt") == 1.0


# ── Strategy: retry_lower_temp ────────────────────────────────────────────────


class TestRetryLowerTempStrategy:
    def test_sets_temperature_hint(self, engine: FallbackStrategyEngine) -> None:
        ctx = _ctx()
        engine.apply(ctx, "retry_lower_temp")
        assert "_temperature_hint" in ctx.stage_start_times
        # Default 1.0 - 0.3 = 0.7
        assert ctx.stage_start_times["_temperature_hint"] == pytest.approx(0.7)

    def test_temperature_does_not_go_below_zero(self, engine: FallbackStrategyEngine) -> None:
        ctx = _ctx()
        ctx.stage_start_times["_temperature_hint"] = 0.1
        engine.apply(ctx, "retry_lower_temp")
        assert ctx.stage_start_times["_temperature_hint"] == pytest.approx(0.0)

    def test_sets_fallback_strategy_applied(self, engine: FallbackStrategyEngine) -> None:
        ctx = _ctx()
        engine.apply(ctx, "retry_lower_temp")
        assert ctx.fallback_strategy_applied == "retry_lower_temp"

    def test_marks_strategy_attempted(self, engine: FallbackStrategyEngine) -> None:
        ctx = _ctx()
        engine.apply(ctx, "retry_lower_temp")
        assert ctx.stage_start_times.get("_attempted:retry_lower_temp") == 1.0


# ── Strategy: rag_augmentation ────────────────────────────────────────────────


class TestRagAugmentationStrategy:
    def test_marks_rag_requested_when_kb_available(
        self, engine: FallbackStrategyEngine
    ) -> None:
        ctx = _ctx(kb_id="kb-abc-123")
        engine.apply(ctx, "rag_augmentation")
        assert ctx.stage_start_times.get("_rag_requested") == 1.0
        assert ctx.fallback_strategy_applied == "rag_augmentation"

    def test_no_rag_flag_when_no_kb(self, engine: FallbackStrategyEngine) -> None:
        ctx = _ctx(kb_id=None)
        engine.apply(ctx, "rag_augmentation")
        assert "_rag_requested" not in ctx.stage_start_times
        assert ctx.fallback_strategy_applied is None

    def test_marks_strategy_attempted_regardless_of_kb(
        self, engine: FallbackStrategyEngine
    ) -> None:
        ctx = _ctx(kb_id=None)
        engine.apply(ctx, "rag_augmentation")
        assert ctx.stage_start_times.get("_attempted:rag_augmentation") == 1.0


# ── Strategy: alternate_model ─────────────────────────────────────────────────


class TestAlternateModelStrategy:
    def test_switches_from_ollama_to_openai(self, engine: FallbackStrategyEngine) -> None:
        ctx = _ctx(model_provider="ollama", model_name="llama3")
        engine.apply(ctx, "alternate_model")
        assert ctx.model_provider == _DEFAULT_ALTERNATE_PROVIDER
        assert ctx.model_name == _DEFAULT_ALTERNATE_MODEL
        assert ctx.fallback_strategy_applied == "alternate_model"

    def test_marks_strategy_attempted(self, engine: FallbackStrategyEngine) -> None:
        ctx = _ctx()
        engine.apply(ctx, "alternate_model")
        assert ctx.stage_start_times.get("_attempted:alternate_model") == 1.0

    def test_already_on_alternate_provider_still_marks_applied(
        self, engine: FallbackStrategyEngine
    ) -> None:
        ctx = _ctx(model_provider="openai", model_name="gpt-4o")
        engine.apply(ctx, "alternate_model")
        # No switch occurs (already on alternate), but strategy is recorded
        assert ctx.fallback_strategy_applied == "alternate_model"
        assert ctx.model_provider == "openai"  # unchanged


# ── Stage output reset (common to all strategies) ─────────────────────────────


class TestStageOutputReset:
    @pytest.mark.parametrize(
        "strategy", ["retry_prompt", "retry_lower_temp", "alternate_model"]
    )
    def test_stage_outputs_cleared(
        self, engine: FallbackStrategyEngine, strategy: str
    ) -> None:
        ctx = _ctx(kb_id="kb-1")
        # Populate outputs
        from sentinel.domain.models.claim import Claim
        ctx.claims = [Claim(index=0, text="test", entity_type=None)]
        ctx.llm_response_text = "old response"

        engine.apply(ctx, strategy)

        assert ctx.llm_response_text is None
        assert ctx.claims == []
        assert ctx.claim_results == []
        assert ctx.safety_results == []
        assert ctx.confidence_score is None
        assert ctx.guardrail_decision is None
        assert ctx.retry_requested is False

    @pytest.mark.parametrize(
        "strategy", ["retry_prompt", "retry_lower_temp", "alternate_model"]
    )
    def test_attempt_number_incremented(
        self, engine: FallbackStrategyEngine, strategy: str
    ) -> None:
        ctx = _ctx(kb_id="kb-1")
        original = ctx.attempt_number
        engine.apply(ctx, strategy)
        assert ctx.attempt_number == original + 1
