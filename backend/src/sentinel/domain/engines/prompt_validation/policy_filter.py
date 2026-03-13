from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sentinel.domain.models.policy import PolicySnapshot


@dataclass(frozen=True)
class PolicyCheckResult:
    status: Literal["pass", "block"]
    violated_category: str | None


class PolicyFilter:
    """Pure domain class — no I/O, no side effects.

    Performs case-insensitive substring match of prompt text against
    ``policy.restricted_categories``.  Injected via constructor; no singletons.
    """

    def check(self, prompt: str, policy: PolicySnapshot) -> PolicyCheckResult:
        """Return :class:`PolicyCheckResult` for *prompt* given *policy*."""
        prompt_lower = prompt.lower()
        for category in policy.restricted_categories:
            if category.lower() in prompt_lower:
                return PolicyCheckResult(
                    status="block",
                    violated_category=category,
                )
        return PolicyCheckResult(status="pass", violated_category=None)
