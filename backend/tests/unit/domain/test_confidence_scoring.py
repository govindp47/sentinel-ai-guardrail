"""Unit tests for ConfidenceScoringEngine.

Covers: all 4 signal paths, neutral defaults, boundary label conditions,
determinism, and score-range invariant.
"""
from __future__ import annotations

import copy

import pytest

from sentinel.domain.engines.confidence_scoring import ConfidenceScoringEngine
from sentinel.domain.models.claim import Claim
from sentinel.domain.models.decision import SafetyFilterResult
from sentinel.domain.models.evidence import ClaimVerificationResult, Evidence
from sentinel.domain.models.pipeline_context import PipelineContext
from sentinel.domain.models.policy import PolicySnapshot


# ── Fixtures and helpers ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine() -> ConfidenceScoringEngine:
    return ConfidenceScoringEngine()


def _policy(accept: int = 70, warn: int = 40, block: int = 0) -> PolicySnapshot:
    return PolicySnapshot(
        accept_threshold=accept,
        warn_threshold=warn,
        block_threshold=block,
    )


def _ctx(
    claim_results: list[ClaimVerificationResult] | None = None,
    safety_results: list[SafetyFilterResult] | None = None,
    llm_response_text: str | None = None,
    policy: PolicySnapshot | None = None,
) -> PipelineContext:
    ctx = PipelineContext(
        request_id="req-test",
        session_id="sess-test",
        original_prompt="test prompt",
        masked_prompt="test prompt",
        model_provider="ollama",
        model_name="llama3",
        kb_id=None,
        policy=policy or _policy(),
    )
    if claim_results is not None:
        ctx.claim_results = claim_results
    if safety_results is not None:
        ctx.safety_results = safety_results
    if llm_response_text is not None:
        ctx.llm_response_text = llm_response_text
    return ctx


def _claim(index: int = 0) -> Claim:
    return Claim(index=index, text=f"Claim {index}", entity_type="fact")


def _evidence(relevance: float) -> Evidence:
    return Evidence(
        chunk_id=f"c-{relevance}",
        chunk_text="Evidence text.",
        document_filename="doc.pdf",
        relevance_score=relevance,
        rank=1,
    )


def _result(status: str, relevance: float = 0.8, index: int = 0) -> ClaimVerificationResult:
    return ClaimVerificationResult(
        claim=_claim(index),
        status=status,  # type: ignore[arg-type]
        evidence=(_evidence(relevance),),
        justification="test",
        confidence_contribution=0.0,
    )


def _safety(result: str, score: float = 0.8) -> SafetyFilterResult:
    return SafetyFilterResult(
        filter_name="toxicity",
        result=result,  # type: ignore[arg-type]
        score=score,
    )


# ── Determinism ───────────────────────────────────────────────────────────────


class TestDeterminism:
    def test_same_context_produces_same_score(self, engine: ConfidenceScoringEngine) -> None:
        ctx = _ctx(
            claim_results=[_result("supported", 0.9), _result("unsupported", 0.5, 1)],
            safety_results=[],
            llm_response_text="word " * 50,
        )
        engine.compute(ctx)
        first_value = ctx.confidence_score.value  # type: ignore[union-attr]
        first_breakdown = ctx.confidence_score.breakdown_as_dict()  # type: ignore[union-attr]

        # Reset score and recompute
        ctx.confidence_score = None
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        assert ctx.confidence_score.value == first_value
        assert ctx.confidence_score.breakdown_as_dict() == first_breakdown

    def test_determinism_1000_iterations(self, engine: ConfidenceScoringEngine) -> None:
        ctx = _ctx(
            claim_results=[_result("supported", 0.85), _result("contradicted", 0.7, 1)],
            safety_results=[_safety("flagged")],
            llm_response_text="word " * 30,
        )
        engine.compute(ctx)
        reference = ctx.confidence_score.value  # type: ignore[union-attr]

        for _ in range(999):
            ctx.confidence_score = None
            engine.compute(ctx)
            assert ctx.confidence_score is not None
            assert ctx.confidence_score.value == reference


# ── Signal scenarios ──────────────────────────────────────────────────────────


class TestAllSupportedClaims:
    def test_all_supported_returns_high_score(self, engine: ConfidenceScoringEngine) -> None:
        ctx = _ctx(
            claim_results=[
                _result("supported", 0.95, 0),
                _result("supported", 0.90, 1),
                _result("supported", 0.88, 2),
            ],
            safety_results=[],
            llm_response_text="word " * 100,
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        assert ctx.confidence_score.value >= 80
        assert ctx.confidence_score.label == "high"


class TestAllContradictedClaims:
    def test_all_contradicted_returns_low_score(self, engine: ConfidenceScoringEngine) -> None:
        ctx = _ctx(
            claim_results=[
                _result("contradicted", 0.9, 0),
                _result("contradicted", 0.85, 1),
            ],
            safety_results=[],
            llm_response_text="word " * 50,
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        assert ctx.confidence_score.value < 40


class TestAllUnsupportedClaims:
    def test_all_unsupported_returns_low_score(self, engine: ConfidenceScoringEngine) -> None:
        # unsupported: evidence_similarity = 0.0, verification ratio normalized = 0.5
        ctx = _ctx(
            claim_results=[
                _result("unsupported", 0.5, 0),
                _result("unsupported", 0.4, 1),
            ],
            safety_results=[],
            llm_response_text="word " * 50,
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        # No supported claims → evidence_similarity = 0.0 → score is pulled down
        assert ctx.confidence_score.value < 60


class TestNoClaims:
    def test_no_claims_returns_neutral_score(self, engine: ConfidenceScoringEngine) -> None:
        ctx = _ctx(claim_results=[], safety_results=[])
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        assert 45 <= ctx.confidence_score.value <= 65

    def test_no_claims_no_response_text(self, engine: ConfidenceScoringEngine) -> None:
        # All signals neutral/no-penalty: score = 0.5*0.35 + 0.5*0.35 + 1.0*0.10 + 1.0*0.20
        # = 0.175 + 0.175 + 0.10 + 0.20 = 0.65 → 65
        ctx = _ctx(claim_results=[], safety_results=[], llm_response_text=None)
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        assert ctx.confidence_score.value == 65


class TestSafetyPenalty:
    def test_one_flagged_filter_reduces_score(self, engine: ConfidenceScoringEngine) -> None:
        baseline = _ctx(claim_results=[], safety_results=[])
        engine.compute(baseline)
        base_score = baseline.confidence_score.value  # type: ignore[union-attr]

        flagged = _ctx(
            claim_results=[],
            safety_results=[SafetyFilterResult(filter_name="toxicity", result="flagged", score=0.9)],
        )
        engine.compute(flagged)
        assert flagged.confidence_score is not None
        assert flagged.confidence_score.value < base_score

    def test_three_flagged_filters_capped(self, engine: ConfidenceScoringEngine) -> None:
        # 3 flags × -0.3 = -0.9, floor is -1.0 → penalty = 0.1, not negative
        ctx = _ctx(
            claim_results=[],
            safety_results=[
                SafetyFilterResult(filter_name="toxicity", result="flagged", score=0.9),
                SafetyFilterResult(filter_name="hate_speech", result="flagged", score=0.8),
                SafetyFilterResult(filter_name="harmful", result="flagged", score=0.7),
            ],
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        # Safety signal = (−0.9 + 1.0) = 0.1
        breakdown = ctx.confidence_score.breakdown_as_dict()
        assert breakdown["safety_penalty"] == pytest.approx(0.1, abs=0.001)

    def test_four_flagged_filters_floor(self, engine: ConfidenceScoringEngine) -> None:
        # 4 flags × -0.3 = -1.2, floored at -1.0 → penalty signal = 0.0
        ctx = _ctx(
            claim_results=[],
            safety_results=[
                SafetyFilterResult(filter_name=f"filter_{i}", result="flagged", score=0.8)
                for i in range(4)
            ],
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        breakdown = ctx.confidence_score.breakdown_as_dict()
        assert breakdown["safety_penalty"] == pytest.approx(0.0, abs=0.001)

    def test_clean_safety_results_no_penalty(self, engine: ConfidenceScoringEngine) -> None:
        ctx = _ctx(
            claim_results=[],
            safety_results=[SafetyFilterResult(filter_name="toxicity", result="clean", score=0.05)],
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        breakdown = ctx.confidence_score.breakdown_as_dict()
        assert breakdown["safety_penalty"] == pytest.approx(1.0, abs=0.001)


class TestClaimDensityPenalty:
    def test_high_density_reduces_signal(self, engine: ConfidenceScoringEngine) -> None:
        # 10 claims in a 20-word response = 50 claims/100 words → heavily penalised
        claims = [_result("supported", 0.9, i) for i in range(10)]
        ctx = _ctx(
            claim_results=claims,
            safety_results=[],
            llm_response_text=" ".join(["word"] * 20),
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        breakdown = ctx.confidence_score.breakdown_as_dict()
        # density_score = max(0, 1 - 50/10) = max(0, -4) = 0.0
        assert breakdown["claim_density_penalty"] == pytest.approx(0.0, abs=0.001)

    def test_low_density_no_penalty(self, engine: ConfidenceScoringEngine) -> None:
        # 2 claims in a 200-word response = 1 claim/100 words → very low density
        claims = [_result("supported", 0.9, i) for i in range(2)]
        ctx = _ctx(
            claim_results=claims,
            safety_results=[],
            llm_response_text=" ".join(["word"] * 200),
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        breakdown = ctx.confidence_score.breakdown_as_dict()
        # density_score = max(0, 1 - 1/10) = 0.9
        assert breakdown["claim_density_penalty"] == pytest.approx(0.9, abs=0.001)

    def test_no_response_text_no_density_penalty(self, engine: ConfidenceScoringEngine) -> None:
        ctx = _ctx(
            claim_results=[_result("supported", 0.9)],
            safety_results=[],
            llm_response_text=None,
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        assert ctx.confidence_score.breakdown_as_dict()["claim_density_penalty"] == 1.0


# ── Label boundary conditions ─────────────────────────────────────────────────


class TestLabelBoundaries:
    def _score_for(self, engine: ConfidenceScoringEngine, target: int, accept: int, warn: int) -> int:
        """Drive the engine with a policy whose accept/warn thresholds are known,
        then inspect the final integer score via a crafted signal set.
        We craft a context that produces a score as close to *target* as possible,
        then verify labelling independently of exact signal math.
        """
        # Use all-neutral signals → score = 65; we'll test label thresholds directly.
        ctx = _ctx(claim_results=[], safety_results=[], policy=_policy(accept=accept, warn=warn))
        engine.compute(ctx)
        return ctx.confidence_score.value  # type: ignore[union-attr]

    def test_score_at_accept_threshold_is_high(self, engine: ConfidenceScoringEngine) -> None:
        # Set accept_threshold=65, warn=40: neutral context always produces 65 → 'high'
        ctx = _ctx(
            claim_results=[], safety_results=[],
            policy=_policy(accept=65, warn=40),
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        assert ctx.confidence_score.value == 65
        assert ctx.confidence_score.label == "high"

    def test_score_below_accept_threshold_is_medium(self, engine: ConfidenceScoringEngine) -> None:
        # Set accept_threshold=66: score 65 < 66 → 'medium'
        ctx = _ctx(
            claim_results=[], safety_results=[],
            policy=_policy(accept=66, warn=40),
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        assert ctx.confidence_score.value == 65
        assert ctx.confidence_score.label == "medium"

    def test_score_at_warn_threshold_is_medium(self, engine: ConfidenceScoringEngine) -> None:
        # Set warn_threshold=65, accept=90: score 65 >= warn(65) → 'medium'
        ctx = _ctx(
            claim_results=[], safety_results=[],
            policy=_policy(accept=90, warn=65),
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        assert ctx.confidence_score.value == 65
        assert ctx.confidence_score.label == "medium"

    def test_score_below_warn_threshold_is_low(self, engine: ConfidenceScoringEngine) -> None:
        # Set warn_threshold=66, accept=90: score 65 < 66 → 'low'
        ctx = _ctx(
            claim_results=[], safety_results=[],
            policy=_policy(accept=90, warn=66),
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        assert ctx.confidence_score.value == 65
        assert ctx.confidence_score.label == "low"


# ── Score-range invariant ─────────────────────────────────────────────────────


class TestScoreRangeInvariant:
    @pytest.mark.parametrize(
        "claim_statuses,n_flagged",
        [
            (["supported"] * 3, 0),
            (["contradicted"] * 3, 2),
            (["unsupported"] * 3, 1),
            ([], 0),
            ([], 3),
            (["supported", "contradicted", "unsupported"], 1),
        ],
    )
    def test_score_always_0_to_100(
        self,
        engine: ConfidenceScoringEngine,
        claim_statuses: list[str],
        n_flagged: int,
    ) -> None:
        ctx = _ctx(
            claim_results=[_result(s, 0.8, i) for i, s in enumerate(claim_statuses)],
            safety_results=[
                SafetyFilterResult(filter_name=f"f{j}", result="flagged", score=0.9)
                for j in range(n_flagged)
            ],
            llm_response_text="word " * 20,
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        assert 0 <= ctx.confidence_score.value <= 100


# ── Signal breakdown completeness ─────────────────────────────────────────────


class TestSignalBreakdown:
    def test_all_four_signal_keys_present(self, engine: ConfidenceScoringEngine) -> None:
        ctx = _ctx(claim_results=[], safety_results=[])
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        keys = set(ctx.confidence_score.breakdown_as_dict().keys())
        assert keys == {
            "evidence_similarity",
            "claim_verification_ratio",
            "claim_density_penalty",
            "safety_penalty",
        }

    def test_signal_values_in_0_1_range(self, engine: ConfidenceScoringEngine) -> None:
        ctx = _ctx(
            claim_results=[_result("supported", 0.9), _result("contradicted", 0.7, 1)],
            safety_results=[SafetyFilterResult(filter_name="tox", result="flagged", score=0.8)],
            llm_response_text="word " * 40,
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        for key, value in ctx.confidence_score.breakdown_as_dict().items():
            assert 0.0 <= value <= 1.0, f"Signal {key} = {value} out of [0,1]"

    def test_confidence_score_is_frozen(self, engine: ConfidenceScoringEngine) -> None:
        import dataclasses
        ctx = _ctx(claim_results=[], safety_results=[])
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.confidence_score.value = 99  # type: ignore[misc]




class TestNeutralAllSignalsExact:
    """Verify the exact neutral score value when all signals take their defaults."""

    def test_neutral_score_is_65(self, engine: ConfidenceScoringEngine) -> None:
        # All signals neutral: evidence_similarity=0.5, claim_verification_ratio=0.5,
        # claim_density_penalty=1.0 (no llm_response_text), safety_penalty=1.0
        # raw = 0.5*0.35 + 0.5*0.35 + 1.0*0.10 + 1.0*0.20 = 0.175+0.175+0.10+0.20 = 0.65
        ctx = _ctx(claim_results=[], safety_results=[], llm_response_text=None)
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        assert ctx.confidence_score.value == 65

    def test_no_claims_with_response_text_no_density_penalty(
        self, engine: ConfidenceScoringEngine
    ) -> None:
        # claim_results=[] and llm_response_text set: density skipped (no claims)
        ctx = _ctx(claim_results=[], safety_results=[], llm_response_text="Some response text here.")
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        breakdown = ctx.confidence_score.breakdown_as_dict()
        assert breakdown["claim_density_penalty"] == pytest.approx(1.0)

    def test_evidence_similarity_zero_when_no_supported_claims(
        self, engine: ConfidenceScoringEngine
    ) -> None:
        # claim_results non-empty but none are 'supported'
        ctx = _ctx(
            claim_results=[_result("unsupported", 0.9), _result("contradicted", 0.8, 1)],
            safety_results=[],
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        breakdown = ctx.confidence_score.breakdown_as_dict()
        assert breakdown["evidence_similarity"] == pytest.approx(0.0)

    def test_two_flagged_safety_filters(self, engine: ConfidenceScoringEngine) -> None:
        # 2 flags × -0.3 = -0.6 → signal = (-0.6 + 1.0) = 0.4
        from sentinel.domain.models.decision import SafetyFilterResult
        ctx = _ctx(
            claim_results=[],
            safety_results=[
                SafetyFilterResult(filter_name="toxicity", result="flagged", score=0.8),
                SafetyFilterResult(filter_name="hate_speech", result="flagged", score=0.75),
            ],
        )
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        breakdown = ctx.confidence_score.breakdown_as_dict()
        assert breakdown["safety_penalty"] == pytest.approx(0.4, abs=0.001)

    def test_empty_evidence_tuple_in_supported_claim(
        self, engine: ConfidenceScoringEngine
    ) -> None:
        # supported claim with no evidence items: max(..., default=0.0) → 0.0
        from sentinel.domain.models.claim import Claim
        from sentinel.domain.models.evidence import ClaimVerificationResult
        claim = Claim(index=0, text="A claim with no evidence", entity_type="fact")
        result = ClaimVerificationResult(
            claim=claim,
            status="supported",
            evidence=(),  # empty tuple
            justification="somehow supported",
            confidence_contribution=0.0,
        )
        ctx = _ctx(claim_results=[result], safety_results=[])
        engine.compute(ctx)
        assert ctx.confidence_score is not None
        breakdown = ctx.confidence_score.breakdown_as_dict()
        assert breakdown["evidence_similarity"] == pytest.approx(0.0)
