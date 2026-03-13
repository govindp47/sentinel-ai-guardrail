from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Claim:
    index: int
    text: str
    entity_type: Literal["fact", "statistic", "date", "entity", "causal"] | None
