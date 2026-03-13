from __future__ import annotations

from sentinel.domain.models.confidence import ConfidenceScore
from sentinel.domain.models.pipeline_context import PipelineContext


class ConfidenceScoringEngine:
    """Pure synchronous confidence scoring engine — no I/O, no side effects.

    Implements the 4-signal weighted aggregation from
    04_DOMAIN_ENGINE_DESIGN.md section 7.2.  The computation is fully
    deterministic: identical PipelineContext state always produces an
    identical ConfidenceScore.
    """

    SIGNAL_WEIGHTS: dict[str, float] = {
        "evidence_similarity": 0.35,
        "claim_verification_ratio": 0.35,
        "claim_density_penalty": 0.10,
        "safety_penalty": 0.20,
    }

    def compute(self, context: PipelineContext) -> PipelineContext:
        """Compute confidence score from *context* state and attach it.

        Mutates ``context.confidence_score`` in-place; returns *context*.
        """
        signals: dict[str, float] = {}

        # ── Signal 1: Evidence Similarity ─────────────────────────────────────
        # Average top-1 evidence relevance across *supported* claims.
        if context.claim_results:
            supported = [r for r in context.claim_results if r.status == "supported"]
            if supported:
                signals["evidence_similarity"] = sum(
                    max(
                        (e.relevance_score for e in r.evidence),
                        default=0.0,
                    )
                    for r in supported
                ) / len(supported)
            else:
                signals["evidence_similarity"] = 0.0
        else:
            signals["evidence_similarity"] = 0.5  # neutral: no claims

        # ── Signal 2: Claim Verification Ratio ────────────────────────────────
        # (supported − contradicted) / total, normalised from [-1,1] to [0,1].
        if context.claim_results:
            n = len(context.claim_results)
            n_supported = sum(1 for r in context.claim_results if r.status == "supported")
            n_contradicted = sum(1 for r in context.claim_results if r.status == "contradicted")
            raw_ratio = (n_supported - n_contradicted) / n
            signals["claim_verification_ratio"] = (raw_ratio + 1.0) / 2.0
        else:
            signals["claim_verification_ratio"] = 0.5  # neutral: no claims

        # ── Signal 3: Claim Density Penalty ───────────────────────────────────
        # High claim density relative to response length lowers the signal.
        # >5 claims per 100 words is considered high density.
        if context.llm_response_text and context.claim_results:
            response_word_count = len(context.llm_response_text.split())
            claim_count = len(context.claim_results)
            claims_per_100_words = (claim_count / max(response_word_count, 1)) * 100
            density_score = max(0.0, 1.0 - (claims_per_100_words / 10.0))
            signals["claim_density_penalty"] = density_score
        else:
            signals["claim_density_penalty"] = 1.0  # no penalty

        # ── Signal 4: Safety Penalty ──────────────────────────────────────────
        # −0.3 per flagged filter, floored at −1.0; normalised to [0, 1].
        flagged_filters = [r for r in context.safety_results if r.result == "flagged"]
        raw_safety_penalty = max(-1.0, len(flagged_filters) * -0.3)
        signals["safety_penalty"] = raw_safety_penalty + 1.0  # 0.0 if fully penalized

        # ── Weighted Aggregation ──────────────────────────────────────────────
        raw_score: float = sum(self.SIGNAL_WEIGHTS[k] * v for k, v in signals.items())

        # Clamp to [0.0, 1.0] then scale to integer [0, 100]
        clamped = max(0.0, min(1.0, raw_score))
        final_score = int(round(clamped * 100))

        # ── Label Classification ──────────────────────────────────────────────
        policy = context.policy
        if final_score >= policy.accept_threshold:
            label = "high"
        elif final_score >= policy.warn_threshold:
            label = "medium"
        else:
            label = "low"

        # Round signal values for storage (4 d.p.)
        rounded_signals = {k: round(v, 4) for k, v in signals.items()}

        context.confidence_score = ConfidenceScore.from_dict(
            value=final_score,
            label=label,  # type: ignore[arg-type]
            signal_breakdown=rounded_signals,
        )
        return context
