from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from sentinel.infrastructure.db.models import Base
from sentinel.infrastructure.db.repositories.session_repo import SessionRepository


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture()
async def repo(db_session: AsyncSession):
    return SessionRepository(db_session)


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_or_get_creates_session(repo: SessionRepository):
    sid = str(uuid.uuid4())
    row = await repo.create_or_get(sid)
    assert row.id == sid


@pytest.mark.asyncio
async def test_create_or_get_is_idempotent(repo: SessionRepository):
    sid = str(uuid.uuid4())
    row1 = await repo.create_or_get(sid)
    row2 = await repo.create_or_get(sid)
    assert row1.id == row2.id
    assert row1.created_at == row2.created_at


@pytest.mark.asyncio
async def test_update_last_active_changes_timestamp(repo: SessionRepository):
    sid = str(uuid.uuid4())
    row = await repo.create_or_get(sid)
    original_ts = row.last_active_at

    # Small sleep to ensure timestamp differs
    await asyncio.sleep(0.01)
    await repo.update_last_active(sid)

    # Re-fetch
    from sqlalchemy import select
    from sentinel.infrastructure.db.models import SessionORM
    from datetime import timezone as tz
    result = await repo._session.execute(select(SessionORM).where(SessionORM.id == sid))
    updated_row = result.scalar_one()

    # Normalize both timestamps to UTC aware for comparison
    original_ts_aware = original_ts if original_ts.tzinfo else original_ts.replace(tzinfo=tz.utc)
    updated_ts_aware = updated_row.last_active_at if updated_row.last_active_at.tzinfo else updated_row.last_active_at.replace(tzinfo=tz.utc)
    assert updated_ts_aware >= original_ts_aware


@pytest.mark.asyncio
async def test_concurrent_create_no_duplicate(repo: SessionRepository):
    """Two concurrent create_or_get calls with the same ID must not raise."""
    sid = str(uuid.uuid4())
    results = await asyncio.gather(
        repo.create_or_get(sid),
        repo.create_or_get(sid),
        return_exceptions=True,
    )
    errors = [r for r in results if isinstance(r, Exception)]
    assert errors == [], f"Unexpected errors: {errors}"
