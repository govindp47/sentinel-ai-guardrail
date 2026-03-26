from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from sentinel.infrastructure.db.models import AnalyticsCounterORM, Base
from sentinel.infrastructure.db.repositories.analytics_repo import AnalyticsRepository
from sentinel.infrastructure.db.repositories.session_repo import SessionRepository


# ── Fixtures ──────────────────────────────────────────────────────────────────


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
async def session_id(db_session: AsyncSession) -> str:
    sid = str(uuid.uuid4())
    repo = SessionRepository(db_session)
    await repo.create_or_get(sid)
    return sid


@pytest_asyncio.fixture()
async def repo(db_session: AsyncSession):
    return AnalyticsRepository(db_session)


async def _fetch_row(
    db: AsyncSession,
    session_id: str,
    date_bucket: str,
    model_provider: str,
    model_name: str,
) -> AnalyticsCounterORM | None:
    result = await db.execute(
        select(AnalyticsCounterORM)
        .where(AnalyticsCounterORM.session_id == session_id)
        .where(AnalyticsCounterORM.date_bucket == date_bucket)
        .where(AnalyticsCounterORM.model_provider == model_provider)
        .where(AnalyticsCounterORM.model_name == model_name)
    )
    return result.scalar_one_or_none()


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_creates_new_row(
    repo: AnalyticsRepository,
    db_session: AsyncSession,
    session_id: str,
):
    await repo.upsert_counters(
        session_id=session_id,
        date_bucket="2024-03-15",
        model_provider="ollama",
        model_name="mistral",
        delta={"total_requests": 1, "total_accepted": 1, "sum_latency_ms": 250},
    )
    row = await _fetch_row(db_session, session_id, "2024-03-15", "ollama", "mistral")
    assert row is not None
    assert row.total_requests == 1
    assert row.total_accepted == 1
    assert row.sum_latency_ms == 250


@pytest.mark.asyncio
async def test_upsert_increments_existing_counters(
    repo: AnalyticsRepository,
    db_session: AsyncSession,
    session_id: str,
):
    kwargs = dict(
        session_id=session_id,
        date_bucket="2024-03-15",
        model_provider="ollama",
        model_name="mistral",
    )
    await repo.upsert_counters(**kwargs, delta={"total_requests": 1, "total_blocked": 1})
    await repo.upsert_counters(**kwargs, delta={"total_requests": 1, "total_blocked": 1})

    row = await _fetch_row(db_session, session_id, "2024-03-15", "ollama", "mistral")
    assert row is not None
    assert row.total_requests == 2
    assert row.total_blocked == 2


@pytest.mark.asyncio
async def test_upsert_different_models_creates_separate_rows(
    repo: AnalyticsRepository,
    db_session: AsyncSession,
    session_id: str,
):
    base = dict(session_id=session_id, date_bucket="2024-03-15")
    await repo.upsert_counters(**base, model_provider="ollama", model_name="mistral", delta={"total_requests": 1})
    await repo.upsert_counters(**base, model_provider="openai", model_name="gpt-4o", delta={"total_requests": 3})

    row_a = await _fetch_row(db_session, session_id, "2024-03-15", "ollama", "mistral")
    row_b = await _fetch_row(db_session, session_id, "2024-03-15", "openai", "gpt-4o")

    assert row_a is not None and row_a.total_requests == 1
    assert row_b is not None and row_b.total_requests == 3


@pytest.mark.asyncio
async def test_upsert_ignores_unknown_delta_keys(
    repo: AnalyticsRepository,
    db_session: AsyncSession,
    session_id: str,
):
    """Unknown delta keys must not raise; known keys still applied."""
    await repo.upsert_counters(
        session_id=session_id,
        date_bucket="2024-03-15",
        model_provider="ollama",
        model_name="llama3",
        delta={"total_requests": 1, "nonexistent_column": 99},
    )
    row = await _fetch_row(db_session, session_id, "2024-03-15", "ollama", "llama3")
    assert row is not None
    assert row.total_requests == 1
