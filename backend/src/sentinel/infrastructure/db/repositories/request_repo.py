"""
RequestRepository — interface Protocol + NotImplementedError stub.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.infrastructure.db.repositories.base import BaseRepository

# ---------------------------------------------------------------------------
# Data-transfer types (lightweight — no ORM model exposure outside infra layer)
# ---------------------------------------------------------------------------


class RequestRow:
    """Placeholder carrier — replaced by a dataclass/TypedDict in Phase 3."""

    ...


class RequestListItem:
    """Placeholder carrier for paginated list results."""

    ...


# ---------------------------------------------------------------------------
# Interface Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class RequestRepositoryProtocol(Protocol):
    async def create(
        self,
        *,
        id: str,
        session_id: str,
        policy_snapshot_id: str,
        prompt_hash: str,
        prompt_masked_text: str,
        pii_detected: bool,
        pii_types_detected: list[str],
        model_provider: str,
        model_name: str,
        kb_document_set_id: str | None,
    ) -> RequestRow: ...

    async def get_by_id(
        self,
        request_id: str,
        session_id: str,
    ) -> RequestRow | None: ...

    async def list_by_session(
        self,
        session_id: str,
        *,
        decision_filter: str | None = None,
        model_filter: str | None = None,
        min_confidence: int | None = None,
        max_confidence: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[RequestListItem], int]: ...

    async def update_status(
        self,
        request_id: str,
        *,
        status: str,
        retry_count: int | None = None,
    ) -> None: ...

    async def update_completed(
        self,
        request_id: str,
        *,
        status: str,
        guardrail_decision: str,
        decision_reason: str | None,
        decision_triggered_rule: str | None,
        confidence_score: int | None,
        confidence_label: str | None,
        confidence_signal_breakdown: dict[str, float] | None,
        risk_score: int | None,
        final_response_text: str | None,
        block_reason: str | None,
        fallback_strategy_used: str | None,
        total_latency_ms: int | None,
        tokens_in: int | None,
        tokens_out: int | None,
        completed_at: datetime,
    ) -> None: ...

    async def get_for_export(
        self,
        session_id: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[RequestRow]: ...


# ---------------------------------------------------------------------------
# Concrete stub
# ---------------------------------------------------------------------------


class RequestRepository(BaseRepository):
    """Stub implementation — all methods raise NotImplementedError (Phase 1)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        *,
        id: str,
        session_id: str,
        policy_snapshot_id: str,
        prompt_hash: str,
        prompt_masked_text: str,
        pii_detected: bool,
        pii_types_detected: list[str],
        model_provider: str,
        model_name: str,
        kb_document_set_id: str | None,
    ) -> RequestRow:
        raise NotImplementedError

    async def get_by_id(
        self,
        request_id: str,
        session_id: str,
    ) -> RequestRow | None:
        raise NotImplementedError

    async def list_by_session(
        self,
        session_id: str,
        *,
        decision_filter: str | None = None,
        model_filter: str | None = None,
        min_confidence: int | None = None,
        max_confidence: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[RequestListItem], int]:
        raise NotImplementedError

    async def update_status(
        self,
        request_id: str,
        *,
        status: str,
        retry_count: int | None = None,
    ) -> None:
        raise NotImplementedError

    async def update_completed(
        self,
        request_id: str,
        *,
        status: str,
        guardrail_decision: str,
        decision_reason: str | None,
        decision_triggered_rule: str | None,
        confidence_score: int | None,
        confidence_label: str | None,
        confidence_signal_breakdown: dict[str, float] | None,
        risk_score: int | None,
        final_response_text: str | None,
        block_reason: str | None,
        fallback_strategy_used: str | None,
        total_latency_ms: int | None,
        tokens_in: int | None,
        tokens_out: int | None,
        completed_at: datetime,
    ) -> None:
        raise NotImplementedError

    async def get_for_export(
        self,
        session_id: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[RequestRow]:
        raise NotImplementedError
