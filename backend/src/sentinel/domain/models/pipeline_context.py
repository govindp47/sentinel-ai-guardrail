from __future__ import annotations

from dataclasses import dataclass, field

from sentinel.domain.models.claim import Claim
from sentinel.domain.models.confidence import ConfidenceScore
from sentinel.domain.models.decision import (
    GuardrailDecision,
    PromptValidationResult,
    SafetyFilterResult,
    TraceStage,
)
from sentinel.domain.models.evidence import ClaimVerificationResult
from sentinel.domain.models.policy import PolicySnapshot


@dataclass
class PipelineContext:
    # ── Required constructor params (8) ──────────────────────────────────────
    request_id: str
    session_id: str
    original_prompt: str
    masked_prompt: str
    model_provider: str
    model_name: str
    kb_id: str | None
    policy: PolicySnapshot

    # ── Execution counter ─────────────────────────────────────────────────────
    attempt_number: int = 1

    # ── Stage outputs (populated as stages complete) ──────────────────────────
    validation_result: PromptValidationResult | None = None
    llm_response_text: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    llm_latency_ms: int | None = None
    claims: list[Claim] = field(default_factory=list)
    claim_results: list[ClaimVerificationResult] = field(default_factory=list)
    safety_results: list[SafetyFilterResult] = field(default_factory=list)
    confidence_score: ConfidenceScore | None = None
    guardrail_decision: GuardrailDecision | None = None
    fallback_strategy_applied: str | None = None

    # ── Trace accumulator ─────────────────────────────────────────────────────
    trace_stages: list[TraceStage] = field(default_factory=list)
    stage_start_times: dict[str, float] = field(default_factory=dict)

    # ── Control flow flags ────────────────────────────────────────────────────
    is_terminal: bool = False
    retry_requested: bool = False

    # ── Control flow methods ──────────────────────────────────────────────────

    def mark_terminal(self) -> None:
        """Signal that no further pipeline stages should execute."""
        self.is_terminal = True
        self.retry_requested = False

    def request_retry(self, strategy: str) -> None:
        """Signal that the orchestrator should retry with the given strategy."""
        self.retry_requested = True
        self.fallback_strategy_applied = strategy
