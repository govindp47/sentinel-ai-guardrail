"""
SessionRepository — interface Protocol + NotImplementedError stub.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.infrastructure.db.repositories.base import BaseRepository


class SessionRow:
    """Placeholder carrier."""

    ...


@runtime_checkable
class SessionRepositoryProtocol(Protocol):
    async def create_or_get(
        self,
        session_id: str,
    ) -> SessionRow: ...

    async def update_last_active(
        self,
        session_id: str,
        last_active_at: datetime,
    ) -> None: ...

    async def get_by_id(
        self,
        session_id: str,
    ) -> SessionRow | None: ...

    async def update_active_policy(
        self,
        session_id: str,
        policy_snapshot_id: str,
    ) -> None: ...


class SessionRepository(BaseRepository):
    """Stub implementation — all methods raise NotImplementedError (Phase 1)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create_or_get(
        self,
        session_id: str,
    ) -> SessionRow:
        raise NotImplementedError

    async def update_last_active(
        self,
        session_id: str,
        last_active_at: datetime,
    ) -> None:
        raise NotImplementedError

    async def get_by_id(
        self,
        session_id: str,
    ) -> SessionRow | None:
        raise NotImplementedError

    async def update_active_policy(
        self,
        session_id: str,
        policy_snapshot_id: str,
    ) -> None:
        raise NotImplementedError
