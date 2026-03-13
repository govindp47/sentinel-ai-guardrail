"""Unit tests for sentinel.domain.models and sentinel.domain.exceptions."""
from __future__ import annotations

import dataclasses
import pytest

from sentinel.domain.exceptions import (
    EmbeddingError,
    KBNotFoundError,
    LLMTimeoutError,
    LLMUnavailableError,
    PipelineStageError,
    PolicyViolationError,
    SentinelBaseError,
    ValidationError,
)
from sentinel.domain.models.claim import Claim
from sentinel.domain.models.confidence import ConfidenceScore
from sentinel.domain.models.decision import (
    GuardrailDecision,
    PromptValidationResult,
    SafetyFilterResult,
    TraceStage,
)
from sentinel.domain.models.evidence import ClaimVerificationResult, Evidence
from sentinel.domain.models.pipeline_context import PipelineContext
from sentinel.domain.models.policy import PolicySnapshot


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_policy(**kwargs: object) -> PolicySnapshot:
    defaults: dict[str, object] = {
        "accept_threshold": 70,
        "warn_threshold": 40,
        "block_threshold": 0,
    }
    defaults.update(kwargs)
    return PolicySnapshot(**defaults)  # type: ignore[arg-type]


def _make_context(**kwargs: object) -> PipelineContext:
    defaults: dict[str, object] = dict(
        request_id="req-1",
        session_id="sess-1",
        original_prompt="Hello",
        masked_prompt="Hello",
        model_provider="ollama",
        model_name="llama3",
        kb_id=None,
        policy=_make_policy(),
    )
    defaults.update(kwargs)
    return PipelineContext(**defaults)  # type: ignore[arg-type]


# ── Frozen value objects — immutability ───────────────────────────────────────


class TestClaimImmutability:
    def test_frozen(self) -> None:
        c = Claim(index=0, text="Paris is in France", entity_type="fact")
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.text = "Berlin is in Germany"  # type: ignore[misc]

    def test_none_entity_type(self) -> None:
        c = Claim(index=1, text="Some claim", entity_type=None)
        assert c.entity_type is None


class TestEvidenceImmutability:
    def test_frozen(self) -> None:
        e = Evidence(
            chunk_id="c1",
            chunk_text="Paris is the capital of France.",
            document_filename="geo.pdf",
            relevance_score=0.92,
            rank=1,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            e.rank = 99  # type: ignore[misc]


class TestClaimVerificationResultImmutability:
    def test_frozen(self) -> None:
        claim = Claim(index=0, text="Paris is in France", entity_type="fact")
        result = ClaimVerificationResult(
            claim=claim,
            status="supported",
            evidence=(),
            justification="Verified via KB.",
            confidence_contribution=0.8,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.status = "unsupported"  # type: ignore[misc]


class TestSafetyFilterResultImmutability:
    def test_frozen(self) -> None:
        sfr = SafetyFilterResult(filter_name="toxicity", result="clean", score=0.05)
        with pytest.raises(dataclasses.FrozenInstanceError):
            sfr.score = 0.99  # type: ignore[misc]


class TestConfidenceScoreImmutability:
    def test_frozen(self) -> None:
        cs = ConfidenceScore.from_dict(
            value=75, label="high", signal_breakdown={"claim": 0.6, "safety": 0.4}
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            cs.value = 50  # type: ignore[misc]

    def test_from_dict_round_trip(self) -> None:
        bd = {"claim": 0.6, "safety": 0.4}
        cs = ConfidenceScore.from_dict(value=75, label="high", signal_breakdown=bd)
        assert cs.breakdown_as_dict() == bd


class TestGuardrailDecisionImmutability:
    def test_frozen(self) -> None:
        gd = GuardrailDecision(
            decision_type="accept",
            reason="Score above threshold",
            triggered_rule=None,
            safety_filter_override=False,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            gd.decision_type = "block"  # type: ignore[misc]


class TestPromptValidationResultImmutability:
    def test_frozen(self) -> None:
        pvr = PromptValidationResult.from_lists(
            injection_result="pass",
            injection_detail=None,
            pii_result="pass",
            pii_types=[],
            policy_result="pass",
            policy_violated_category=None,
            risk_score=10,
            overall_status="pass",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            pvr.risk_score = 99  # type: ignore[misc]


class TestTraceStage:
    def test_frozen(self) -> None:
        ts = TraceStage.from_dict(
            stage_name="injection_detection",
            duration_ms=12.5,
            metadata={"pattern": "sql"},
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            ts.stage_name = "other"  # type: ignore[misc]

    def test_metadata_round_trip(self) -> None:
        meta = {"pattern": "sql", "score": 0.9}
        ts = TraceStage.from_dict("injection_detection", 12.5, meta)
        assert ts.metadata_as_dict() == meta

    def test_creation_fields(self) -> None:
        ts = TraceStage.from_dict("confidence_scoring", 55.0, {"value": 72})
        assert ts.stage_name == "confidence_scoring"
        assert ts.duration_ms == 55.0


# ── PolicySnapshot validation ─────────────────────────────────────────────────


class TestPolicySnapshotValidation:
    def test_valid_thresholds(self) -> None:
        p = PolicySnapshot(accept_threshold=70, warn_threshold=40, block_threshold=0)
        assert p.accept_threshold == 70

    def test_block_equals_warn_raises(self) -> None:
        with pytest.raises(ValueError, match="block_threshold"):
            PolicySnapshot(accept_threshold=70, warn_threshold=40, block_threshold=40)

    def test_warn_equals_accept_raises(self) -> None:
        with pytest.raises(ValueError, match="warn_threshold"):
            PolicySnapshot(accept_threshold=70, warn_threshold=70, block_threshold=0)

    def test_block_greater_than_warn_raises(self) -> None:
        with pytest.raises(ValueError, match="block_threshold"):
            PolicySnapshot(accept_threshold=70, warn_threshold=30, block_threshold=50)

    def test_warn_greater_than_accept_raises(self) -> None:
        with pytest.raises(ValueError, match="warn_threshold"):
            PolicySnapshot(accept_threshold=40, warn_threshold=70, block_threshold=0)

    def test_all_equal_raises(self) -> None:
        with pytest.raises(ValueError):
            PolicySnapshot(accept_threshold=50, warn_threshold=50, block_threshold=50)

    def test_mutable(self) -> None:
        p = _make_policy()
        p.accept_threshold = 80  # must not raise
        assert p.accept_threshold == 80

    def test_default_list_fields_not_shared(self) -> None:
        p1 = PolicySnapshot()
        p2 = PolicySnapshot()
        p1.restricted_categories.append("violence")
        assert p2.restricted_categories == []


# ── PipelineContext defaults ───────────────────────────────────────────────────


class TestPipelineContextDefaults:
    def test_list_fields_empty_not_none(self) -> None:
        ctx = _make_context()
        assert ctx.claims == []
        assert ctx.claim_results == []
        assert ctx.safety_results == []
        assert ctx.trace_stages == []

    def test_dict_fields_empty_not_none(self) -> None:
        ctx = _make_context()
        assert ctx.stage_start_times == {}

    def test_list_fields_not_shared(self) -> None:
        ctx1 = _make_context()
        ctx2 = _make_context()
        ctx1.claims.append(Claim(index=0, text="test", entity_type=None))
        assert ctx2.claims == []

    def test_optional_fields_none(self) -> None:
        ctx = _make_context()
        assert ctx.validation_result is None
        assert ctx.llm_response_text is None
        assert ctx.confidence_score is None
        assert ctx.guardrail_decision is None
        assert ctx.fallback_strategy_applied is None

    def test_control_flags_default_false(self) -> None:
        ctx = _make_context()
        assert ctx.is_terminal is False
        assert ctx.retry_requested is False

    def test_attempt_number_default(self) -> None:
        ctx = _make_context()
        assert ctx.attempt_number == 1


# ── PipelineContext state transitions ─────────────────────────────────────────


class TestPipelineContextStateTransitions:
    def test_mark_terminal(self) -> None:
        ctx = _make_context()
        ctx.retry_requested = True  # ensure it gets cleared
        ctx.mark_terminal()
        assert ctx.is_terminal is True
        assert ctx.retry_requested is False

    def test_request_retry(self) -> None:
        ctx = _make_context()
        ctx.request_retry("retry_prompt")
        assert ctx.retry_requested is True
        assert ctx.fallback_strategy_applied == "retry_prompt"

    def test_request_retry_alternate_strategy(self) -> None:
        ctx = _make_context()
        ctx.request_retry("rag_augmentation")
        assert ctx.fallback_strategy_applied == "rag_augmentation"

    def test_mark_terminal_after_retry(self) -> None:
        ctx = _make_context()
        ctx.request_retry("retry_prompt")
        ctx.mark_terminal()
        assert ctx.is_terminal is True
        assert ctx.retry_requested is False


# ── Domain exceptions ─────────────────────────────────────────────────────────


class TestDomainExceptions:
    def test_sentinel_base_error(self) -> None:
        exc = SentinelBaseError("base error", stage="test", attempt=1)
        assert exc.message == "base error"
        assert exc.context["stage"] == "test"
        assert exc.context["attempt"] == 1

    def test_pipeline_stage_error(self) -> None:
        cause = RuntimeError("inner")
        exc = PipelineStageError("stage failed", stage_name="injection_detection", cause=cause)
        assert exc.stage_name == "injection_detection"
        assert exc.cause is cause
        assert exc.context["stage_name"] == "injection_detection"

    def test_llm_timeout_error(self) -> None:
        exc = LLMTimeoutError("timeout", provider="ollama", timeout_seconds=30.0)
        assert exc.provider == "ollama"
        assert exc.timeout_seconds == 30.0
        assert exc.context["timeout_seconds"] == 30.0

    def test_llm_unavailable_error(self) -> None:
        exc = LLMUnavailableError("unreachable", provider="openai")
        assert exc.provider == "openai"
        assert exc.context["provider"] == "openai"

    def test_embedding_error(self) -> None:
        exc = EmbeddingError("embed failed", model_name="minilm")
        assert exc.model_name == "minilm"
        assert exc.context["model_name"] == "minilm"

    def test_kb_not_found_error(self) -> None:
        exc = KBNotFoundError("kb missing", kb_id="kb-abc-123")
        assert exc.kb_id == "kb-abc-123"
        assert exc.context["kb_id"] == "kb-abc-123"

    def test_policy_violation_error(self) -> None:
        exc = PolicyViolationError("blocked", violated_category="violence", risk_score=95)
        assert exc.violated_category == "violence"
        assert exc.risk_score == 95
        assert exc.context["risk_score"] == 95

    def test_validation_error(self) -> None:
        exc = ValidationError("bad field", field="prompt", received_value="")
        assert exc.field == "prompt"
        assert exc.received_value == ""
        assert exc.context["field"] == "prompt"

    def test_exceptions_are_subclasses(self) -> None:
        assert issubclass(PipelineStageError, SentinelBaseError)
        assert issubclass(LLMTimeoutError, SentinelBaseError)
        assert issubclass(LLMUnavailableError, SentinelBaseError)
        assert issubclass(EmbeddingError, SentinelBaseError)
        assert issubclass(KBNotFoundError, SentinelBaseError)
        assert issubclass(PolicyViolationError, SentinelBaseError)
        assert issubclass(ValidationError, SentinelBaseError)


class TestDomainExceptionsStringRepresentation:
    """Verify exception __str__ and context dict for structlog integration."""

    def test_sentinel_base_error_str(self) -> None:
        exc = SentinelBaseError("something went wrong", module="domain")
        assert "something went wrong" in str(exc)

    def test_pipeline_stage_error_str(self) -> None:
        exc = PipelineStageError("stage failed", stage_name="confidence_scoring", cause=None)
        assert "stage failed" in str(exc)
        assert exc.context["stage_name"] == "confidence_scoring"

    def test_pipeline_stage_error_cause_none(self) -> None:
        exc = PipelineStageError("failed", stage_name="injection_detection", cause=None)
        assert exc.cause is None
        assert exc.context["cause"] == "None"

    def test_llm_timeout_error_context(self) -> None:
        exc = LLMTimeoutError("timeout", provider="ollama", timeout_seconds=30.0)
        assert exc.context["provider"] == "ollama"
        assert exc.context["timeout_seconds"] == 30.0

    def test_all_exceptions_inherit_sentinel_base(self) -> None:
        exceptions = [
            PipelineStageError("e", stage_name="s", cause=None),
            LLMTimeoutError("e", provider="p", timeout_seconds=5.0),
            LLMUnavailableError("e", provider="p"),
            EmbeddingError("e", model_name="m"),
            KBNotFoundError("e", kb_id="kb-1"),
            PolicyViolationError("e", violated_category="v", risk_score=90),
            ValidationError("e", field="f"),
        ]
        for exc in exceptions:
            assert isinstance(exc, SentinelBaseError)
            assert isinstance(exc.context, dict)
            assert len(str(exc)) > 0

    def test_policy_snapshot_default_module_flags(self) -> None:
        p = PolicySnapshot()
        assert p.module_flags["injection_detection"] is True
        assert p.module_flags["safety_filters"] is True

    def test_policy_snapshot_default_fallback_priority(self) -> None:
        p = PolicySnapshot()
        assert "retry_prompt" in p.fallback_priority
        assert len(p.fallback_priority) == 4

    def test_pipeline_context_kb_id_none(self) -> None:
        from sentinel.domain.models.policy import PolicySnapshot as PS
        ctx = PipelineContext(
            request_id="r",
            session_id="s",
            original_prompt="p",
            masked_prompt="p",
            model_provider="ollama",
            model_name="llama3",
            kb_id=None,
            policy=PS(),
        )
        assert ctx.kb_id is None
