"""
BaseRepository — shared async session lifecycle management.

All concrete repositories inherit from this class.
Session is injected via constructor; repositories never create their own sessions.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """
    Thin base providing session access and transaction helpers.

    Subclasses call self._session directly for queries, and use
    _flush() / _commit() / _rollback() for lifecycle control.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _flush(self) -> None:
        """Flush pending ORM changes to the DB without committing."""
        await self._session.flush()

    async def _commit(self) -> None:
        """Commit the current transaction."""
        await self._session.commit()

    async def _rollback(self) -> None:
        """Roll back the current transaction."""
        await self._session.rollback()
