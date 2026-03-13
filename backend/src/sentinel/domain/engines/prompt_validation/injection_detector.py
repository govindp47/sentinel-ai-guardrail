from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


@dataclass(frozen=True)
class InjectionCheckResult:
    status: Literal["pass", "flag", "block"]
    detail: str | None


class InjectionDetector:
    """Pure domain class — no I/O, no side effects.

    All patterns are compiled once at instantiation.
    ``check()`` normalises the prompt (lowercase + collapsed whitespace)
    before matching so callers do not need to pre-process.
    """

    # High-confidence patterns → BLOCK
    _BLOCK_PATTERN_STRINGS: list[str] = [
        r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
        r"you\s+are\s+now\s+(a\s+)?(?!sentinelai)",  # role override (negative lookahead)
        r"(system|assistant)\s*:\s*",  # message-boundary injection
        r"<\s*/?system\s*>",  # XML role tags
        r"forget\s+your\s+(previous\s+)?(instructions|training)",
        r"do\s+anything\s+now",  # DAN
        r"jailbreak",
        r"pretend\s+you\s+(are|have\s+no)",
    ]

    # Medium-confidence patterns → FLAG
    _FLAG_PATTERN_STRINGS: list[str] = [
        r"disregard\s+",
        r"bypass\s+(your\s+)?(safety|filter|guardrail)",
        r"act\s+as\s+if\s+you\s+(have\s+no|are\s+not)",
        r"hypothetically\s+speaking.*?instructions",
        r"roleplay\s+as",
        r"for\s+educational\s+purposes\s+only.*?(how|explain)",
    ]

    def __init__(self) -> None:
        self._block_patterns: list[re.Pattern[str]] = [
            re.compile(p, re.IGNORECASE) for p in self._BLOCK_PATTERN_STRINGS
        ]
        self._flag_patterns: list[re.Pattern[str]] = [
            re.compile(p, re.IGNORECASE | re.DOTALL) for p in self._FLAG_PATTERN_STRINGS
        ]

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self, prompt: str) -> InjectionCheckResult:
        """Return an :class:`InjectionCheckResult` for *prompt*.

        Processing order: BLOCK patterns first (highest priority), then FLAG.
        """
        normalized = self._normalize(prompt)

        for pattern in self._block_patterns:
            if pattern.search(normalized):
                return InjectionCheckResult(
                    status="block",
                    detail=f"Injection pattern detected: {pattern.pattern[:60]}",
                )

        flag_hits: list[str] = []
        for pattern in self._flag_patterns:
            if pattern.search(normalized):
                flag_hits.append(pattern.pattern[:60])

        if flag_hits:
            return InjectionCheckResult(
                status="flag",
                detail=f"Suspicious patterns: {flag_hits}",
            )

        return InjectionCheckResult(status="pass", detail=None)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(prompt: str) -> str:
        """Lowercase and collapse internal whitespace."""
        return re.sub(r"\s+", " ", prompt.lower()).strip()
