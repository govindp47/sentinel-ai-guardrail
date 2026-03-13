"""
AnalyticsRepository — interface Protocol + NotImplementedError stub.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.infrastructure.db.repositories.base import BaseRepository


class AnalyticsSummaryRow:
    """Placeholder carrier for aggregate query results."""

    ...


class AnalyticsDailyRow:
    """Placeholder carrier for daily breakdown rows."""

    ...


@runtime_checkable
class AnalyticsRepositoryProtocol(Protocol):
    async def upsert_counters(
        self,
        *,
        id: str,
        session_id: str,
        date_bucket: str,
        model_provider: str,
        model_name: str,
        accepted: bool,
        warned: bool,
        retried: bool,
        blocked: bool,
        hallucination_detected: bool,
        safety_triggered: bool,
        confidence_score: int,
        latency_ms: int,
        tokens_in: int,
        tokens_out: int,
    ) -> None: ...

    async def get_summary_by_session(
        self,
        session_id: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        model_provider: str | None = None,
    ) -> list[AnalyticsSummaryRow]: ...

    async def get_daily_breakdown(
        self,
        session_id: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[AnalyticsDailyRow]: ...


class AnalyticsRepository(BaseRepository):
    """Stub implementation — all methods raise NotImplementedError (Phase 1)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def upsert_counters(
        self,
        *,
        id: str,
        session_id: str,
        date_bucket: str,
        model_provider: str,
        model_name: str,
        accepted: bool,
        warned: bool,
        retried: bool,
        blocked: bool,
        hallucination_detected: bool,
        safety_triggered: bool,
        confidence_score: int,
        latency_ms: int,
        tokens_in: int,
        tokens_out: int,
    ) -> None:
        raise NotImplementedError

    async def get_summary_by_session(
        self,
        session_id: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        model_provider: str | None = None,
    ) -> list[AnalyticsSummaryRow]:
        raise NotImplementedError

    async def get_daily_breakdown(
        self,
        session_id: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[AnalyticsDailyRow]:
        raise NotImplementedError
