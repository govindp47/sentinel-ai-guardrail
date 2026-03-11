"""
Async SQLAlchemy engine and session factory.

Creates a single engine bound to the DATABASE_URL from AppConfig.
SQLite: WAL journal mode + NullPool (SQLite cannot share pool connections).
PostgreSQL: default AsyncAdaptedQueuePool.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
import sqlite3

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool


def _build_engine(database_url: str, echo: bool = False) -> AsyncEngine:
    is_sqlite = database_url.startswith("sqlite")

    engine = create_async_engine(
        database_url,
        echo=echo,
        poolclass=NullPool if is_sqlite else AsyncAdaptedQueuePool,
    )

    if is_sqlite:
        # Enable WAL mode and foreign keys on every new SQLite connection.
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn: sqlite3.Connection, _connection_record: object) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return engine


def create_engine_from_config() -> AsyncEngine:
    """Create the async engine using AppConfig.database_url."""
    import os
    import sys

    _src = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    if _src not in sys.path:
        sys.path.insert(0, _src)

    from sentinel.config import AppConfig

    config = AppConfig()
    return _build_engine(config.database_url, echo=False)


# Module-level engine and session factory.
# Replaced at application startup via init_db() if needed.
_engine: AsyncEngine | None = None
_AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_engine_from_config()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _AsyncSessionLocal = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _AsyncSessionLocal


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency-injectable async session.
    Usage in FastAPI:  session: AsyncSession = Depends(get_session)
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session
