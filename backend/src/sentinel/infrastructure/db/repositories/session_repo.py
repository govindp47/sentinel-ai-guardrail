from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.infrastructure.db.models import SessionORM


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_or_get(self, session_id: str) -> SessionORM:
        """
        Idempotent session creation using INSERT OR IGNORE (SQLite dialect).
        Safe under concurrent calls with the same session_id.
        """
        stmt = (
            sqlite_insert(SessionORM)
            .values(
                id=session_id,
                created_at=datetime.now(UTC),
                last_active_at=datetime.now(UTC),
            )
            .prefix_with("OR IGNORE")
        )
        await self._session.execute(stmt)
        await self._session.flush()

        result = await self._session.execute(select(SessionORM).where(SessionORM.id == session_id))
        row = result.scalar_one()
        return row

    async def update_last_active(self, session_id: str) -> None:
        """
        Single-statement timestamp update — no read-then-write.
        """
        stmt = (
            update(SessionORM)
            .where(SessionORM.id == session_id)
            .values(last_active_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)
        await self._session.flush()
