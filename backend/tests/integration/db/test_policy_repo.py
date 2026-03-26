from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from sentinel.domain.models.policy import PolicySnapshot
from sentinel.infrastructure.db.models import Base
from sentinel.infrastructure.db.repositories.policy_repo import PolicyRepository
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
    return PolicyRepository(db_session)


def _default_policy(**overrides) -> PolicySnapshot:
    base = PolicySnapshot(
        accept_threshold=70,
        warn_threshold=40,
        block_threshold=0,
        max_retries=2,
        restricted_categories=["violence", "hate_speech"],
        allowed_topics=[],
        fallback_priority=["retry_prompt", "retry_lower_temp"],
        module_flags={"injection_detection": True, "pii_detection": False},
    )
    for k, v in overrides.items():
        object.__setattr__(base, k, v)
    return base


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_snapshot_returns_uuid(
    repo: PolicyRepository, session_id: str
):
    policy = _default_policy()
    snapshot_id = await repo.create_snapshot(session_id, policy)
    assert isinstance(snapshot_id, str)
    assert len(snapshot_id) == 36  # UUID4 format


@pytest.mark.asyncio
async def test_get_latest_returns_none_when_no_snapshots(
    repo: PolicyRepository, session_id: str
):
    result = await repo.get_latest_for_session(session_id)
    assert result is None


@pytest.mark.asyncio
async def test_get_latest_returns_correct_object(
    repo: PolicyRepository, session_id: str
):
    policy = _default_policy()
    await repo.create_snapshot(session_id, policy)
    retrieved = await repo.get_latest_for_session(session_id)

    assert retrieved is not None
    assert retrieved.accept_threshold == 70
    assert retrieved.restricted_categories == ["violence", "hate_speech"]
    assert isinstance(retrieved.restricted_categories, list)
    assert isinstance(retrieved.module_flags, dict)
    assert retrieved.module_flags["pii_detection"] is False


@pytest.mark.asyncio
async def test_get_latest_returns_most_recent(
    repo: PolicyRepository, session_id: str
):
    policy_v1 = _default_policy(accept_threshold=80, warn_threshold=50, block_threshold=10)
    policy_v2 = _default_policy(accept_threshold=90, warn_threshold=60, block_threshold=20)

    await repo.create_snapshot(session_id, policy_v1)
    await repo.create_snapshot(session_id, policy_v2)

    latest = await repo.get_latest_for_session(session_id)
    assert latest is not None
    assert latest.accept_threshold == 90


@pytest.mark.asyncio
async def test_json_fields_deserialize_to_correct_types(
    repo: PolicyRepository, session_id: str
):
    policy = _default_policy(
        restricted_categories=["a", "b", "c"],
        fallback_priority=["retry_prompt"],
        module_flags={"injection_detection": True},
    )
    await repo.create_snapshot(session_id, policy)
    result = await repo.get_latest_for_session(session_id)

    assert result is not None
    assert type(result.restricted_categories) is list
    assert type(result.fallback_priority) is list
    assert type(result.module_flags) is dict
