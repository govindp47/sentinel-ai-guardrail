"""
PolicyRepository — interface Protocol + NotImplementedError stub.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.infrastructure.db.repositories.base import BaseRepository


class PolicySnapshotRow:
    """Placeholder carrier."""

    ...


@runtime_checkable
class PolicyRepositoryProtocol(Protocol):
    async def create_snapshot(
        self,
        *,
        id: str,
        session_id: str,
        accept_threshold: int,
        warn_threshold: int,
        block_threshold: int,
        max_retries: int,
        restricted_categories: list[str],
        allowed_topics: list[str],
        fallback_priority: list[str],
        module_flags: dict[str, bool],
    ) -> PolicySnapshotRow: ...

    async def get_latest_for_session(
        self,
        session_id: str,
    ) -> PolicySnapshotRow | None: ...

    async def get_by_id(
        self,
        snapshot_id: str,
    ) -> PolicySnapshotRow | None: ...


class PolicyRepository(BaseRepository):
    """Stub implementation — all methods raise NotImplementedError (Phase 1)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create_snapshot(
        self,
        *,
        id: str,
        session_id: str,
        accept_threshold: int,
        warn_threshold: int,
        block_threshold: int,
        max_retries: int,
        restricted_categories: list[str],
        allowed_topics: list[str],
        fallback_priority: list[str],
        module_flags: dict[str, bool],
    ) -> PolicySnapshotRow:
        raise NotImplementedError

    async def get_latest_for_session(
        self,
        session_id: str,
    ) -> PolicySnapshotRow | None:
        raise NotImplementedError

    async def get_by_id(
        self,
        snapshot_id: str,
    ) -> PolicySnapshotRow | None:
        raise NotImplementedError
