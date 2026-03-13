from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


@dataclass(frozen=True)
class PIICheckResult:
    status: Literal["pass", "flag"]
    pii_types: tuple[str, ...]  # tuple keeps the frozen dataclass hashable
    masked_text: str

    @classmethod
    def clean(cls, original_prompt: str) -> PIICheckResult:
        return cls(status="pass", pii_types=(), masked_text=original_prompt)


class PIIDetector:
    """Pure domain class — no I/O, no side effects.

    All patterns are compiled once at instantiation.

    ``check()``  → returns detected PII types and a masked copy.
    ``mask()``   → convenience wrapper returning only the masked string.

    The replacement token format is ``[REDACTED_<TYPE>]`` (upper-cased type).
    """

    _PATTERN_STRINGS: dict[str, str] = {
        "email": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
        "phone_us": r"\b(\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        # SSN: must be exactly NNN-NN-NNNN or NNN NN NNNN — not longer numeric runs
        "ssn": r"\b\d{3}([-\s])\d{2}\1\d{4}\b",
        # Visa (13/16), Mastercard (16), Amex (15)
        "credit_card": (r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b"),
        # OpenAI-style sk- keys and Google AIza keys only (avoids hex-hash false positives)
        "api_key": r"\b(sk-[a-zA-Z0-9]{32,}|AIza[a-zA-Z0-9_\-]{35})\b",
        "ipv4": (
            r"\b(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]\d|\d)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]\d|\d)\b"
        ),
    }

    def __init__(self) -> None:
        # Ordered dict preserves insertion order (Python 3.7+).
        # Pattern priority matters: more-specific patterns first avoids partial
        # matches from stomping on each other during sequential masking.
        self._patterns: dict[str, re.Pattern[str]] = {
            pii_type: re.compile(pattern) for pii_type, pattern in self._PATTERN_STRINGS.items()
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self, prompt: str) -> PIICheckResult:
        """Scan *prompt* for PII and return a :class:`PIICheckResult`.

        All detected PII tokens are replaced with ``[REDACTED_<TYPE>]`` in
        ``result.masked_text``.  The original prompt is never mutated.
        """
        if not prompt:
            return PIICheckResult.clean(prompt)

        detected: list[str] = []
        working = prompt

        for pii_type, pattern in self._patterns.items():
            matches = list(pattern.finditer(working))
            if matches:
                detected.append(pii_type)
                replacement = f"[REDACTED_{pii_type.upper()}]"
                # Iterate in reverse so replacement doesn't shift earlier offsets.
                for match in reversed(matches):
                    working = working[: match.start()] + replacement + working[match.end() :]

        if detected:
            return PIICheckResult(
                status="flag",
                pii_types=tuple(detected),
                masked_text=working,
            )
        return PIICheckResult.clean(prompt)

    def mask(self, prompt: str) -> str:
        """Return *prompt* with all detected PII replaced by redaction tokens."""
        return self.check(prompt).masked_text
