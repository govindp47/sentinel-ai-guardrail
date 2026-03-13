from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SafetyFilterResult:
    filter_name: str
    result: Literal["clean", "flagged"]
    score: float  # 0.0–1.0


@dataclass(frozen=True)
class GuardrailDecision:
    decision_type: Literal[
        "accept",
        "accept_with_warning",
        "retry_prompt",
        "retry_alternate_model",
        "trigger_rag",
        "block",
    ]
    reason: str
    triggered_rule: str | None
    safety_filter_override: bool  # True if safety filter forced block over confidence


@dataclass(frozen=True)
class PromptValidationResult:
    injection_result: Literal["pass", "flag", "block"]
    injection_detail: str | None
    pii_result: Literal["pass", "flag", "block"]
    pii_types: tuple[str, ...]  # tuple for frozen-dataclass hashability
    policy_result: Literal["pass", "flag", "block"]
    policy_violated_category: str | None
    risk_score: int  # 0–100
    overall_status: Literal["pass", "flag", "block"]

    @classmethod
    def from_lists(
        cls,
        injection_result: Literal["pass", "flag", "block"],
        injection_detail: str | None,
        pii_result: Literal["pass", "flag", "block"],
        pii_types: list[str],
        policy_result: Literal["pass", "flag", "block"],
        policy_violated_category: str | None,
        risk_score: int,
        overall_status: Literal["pass", "flag", "block"],
    ) -> PromptValidationResult:
        return cls(
            injection_result=injection_result,
            injection_detail=injection_detail,
            pii_result=pii_result,
            pii_types=tuple(pii_types),
            policy_result=policy_result,
            policy_violated_category=policy_violated_category,
            risk_score=risk_score,
            overall_status=overall_status,
        )


@dataclass(frozen=True)
class TraceStage:
    stage_name: str
    duration_ms: float
    metadata: tuple[tuple[str, object], ...]  # ((key, value), ...) — frozen-safe

    @classmethod
    def from_dict(
        cls,
        stage_name: str,
        duration_ms: float,
        metadata: dict[str, object],
    ) -> TraceStage:
        return cls(
            stage_name=stage_name,
            duration_ms=duration_ms,
            metadata=tuple(metadata.items()),
        )

    def metadata_as_dict(self) -> dict[str, object]:
        return dict(self.metadata)
