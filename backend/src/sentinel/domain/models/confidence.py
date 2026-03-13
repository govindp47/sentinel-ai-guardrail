from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ConfidenceScore:
    value: int  # 0–100
    label: Literal["high", "medium", "low"]
    signal_breakdown: tuple[tuple[str, float], ...]  # ((signal_name, contribution), ...)

    @classmethod
    def from_dict(
        cls,
        value: int,
        label: Literal["high", "medium", "low"],
        signal_breakdown: dict[str, float],
    ) -> ConfidenceScore:
        """Convenience constructor accepting a plain dict for signal_breakdown."""
        return cls(
            value=value,
            label=label,
            signal_breakdown=tuple(signal_breakdown.items()),
        )

    def breakdown_as_dict(self) -> dict[str, float]:
        return dict(self.signal_breakdown)
