from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PolicySnapshot:
    accept_threshold: int = 70
    warn_threshold: int = 40
    block_threshold: int = 0
    max_retries: int = 2
    restricted_categories: list[str] = field(default_factory=list)
    allowed_topics: list[str] = field(default_factory=list)
    fallback_priority: list[str] = field(
        default_factory=lambda: [
            "retry_prompt",
            "retry_lower_temp",
            "rag_augmentation",
            "alternate_model",
        ]
    )
    module_flags: dict[str, bool] = field(
        default_factory=lambda: {
            "injection_detection": True,
            "pii_detection": True,
            "policy_filter": True,
            "hallucination_detection": True,
            "safety_filters": True,
        }
    )

    def __post_init__(self) -> None:
        if not (self.block_threshold < self.warn_threshold):
            raise ValueError(
                f"PolicySnapshot invariant violated: block_threshold ({self.block_threshold}) "
                f"must be strictly less than warn_threshold ({self.warn_threshold})."
            )
        if not (self.warn_threshold < self.accept_threshold):
            raise ValueError(
                f"PolicySnapshot invariant violated: warn_threshold ({self.warn_threshold}) "
                f"must be strictly less than accept_threshold ({self.accept_threshold})."
            )
