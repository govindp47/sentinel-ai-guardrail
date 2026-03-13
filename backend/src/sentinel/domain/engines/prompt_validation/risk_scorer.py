from __future__ import annotations

from sentinel.domain.engines.prompt_validation.injection_detector import (
    InjectionCheckResult,
)
from sentinel.domain.engines.prompt_validation.pii_detector import PIICheckResult
from sentinel.domain.engines.prompt_validation.policy_filter import PolicyCheckResult


class RiskScorer:
    """Pure domain class — no I/O, no side effects.

    Weighted signal aggregation:
        injection block  → +60
        injection flag   → +30
        pii flag         → +15
        policy block     → +50

    Output is clamped to [0, 100].
    """

    WEIGHTS: dict[str, int] = {
        "injection_block": 60,
        "injection_flag": 30,
        "pii_flag": 15,
        "policy_block": 50,
    }

    def score(
        self,
        injection_result: InjectionCheckResult,
        pii_result: PIICheckResult,
        policy_result: PolicyCheckResult,
    ) -> int:
        """Return an integer risk score in [0, 100]."""
        total = 0

        if injection_result.status == "block":
            total += self.WEIGHTS["injection_block"]
        elif injection_result.status == "flag":
            total += self.WEIGHTS["injection_flag"]

        if pii_result.status == "flag":
            total += self.WEIGHTS["pii_flag"]

        if policy_result.status == "block":
            total += self.WEIGHTS["policy_block"]

        return min(total, 100)
