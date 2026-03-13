from __future__ import annotations

from dataclasses import dataclass

from sentinel.domain.models.claim import Claim


@dataclass(frozen=True)
class Evidence:
    chunk_id: str
    chunk_text: str
    document_filename: str
    relevance_score: float  # cosine similarity, 0.0–1.0
    rank: int


@dataclass(frozen=True)
class ClaimVerificationResult:
    claim: Claim
    status: str  # 'supported' | 'unsupported' | 'contradicted' | 'unverified'
    evidence: tuple[Evidence, ...]  # tuple for hashability inside frozen dataclass
    justification: str
    confidence_contribution: float  # this claim's weighted score contribution
