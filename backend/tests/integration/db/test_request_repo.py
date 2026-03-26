from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from sentinel.infrastructure.db.models import Base
from sentinel.infrastructure.db.repositories.request_repo import (
    RequestDetail,
    RequestRepository,
    RequestSummary,
)
from sentinel.infrastructure.db.repositories.session_repo import SessionRepository
from sentinel.infrastructure.db.repositories.policy_repo import PolicyRepository
from sentinel.domain.models.policy import PolicySnapshot


# ── Shared fixtures ───────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture()
async def seeded_ids(db_session: AsyncSession) -> dict[str, str]:
    """Creates a session + policy snapshot and returns their IDs."""
    sid = str(uuid.uuid4())
    await SessionRepository(db_session).create_or_get(sid)

    policy = PolicySnapshot(
        accept_threshold=70,
        warn_threshold=40,
        block_threshold=0,
    )
    snap_id = await PolicyRepository(db_session).create_snapshot(sid, policy)
    return {"session_id": sid, "policy_snapshot_id": snap_id}


@pytest_asyncio.fixture()
async def repo(db_session: AsyncSession):
    return RequestRepository(db_session)


def _make_request_kwargs(seeded: dict[str, str], **overrides) -> dict:
    base = dict(
        session_id=seeded["session_id"],
        policy_snapshot_id=seeded["policy_snapshot_id"],
        prompt_hash="abc123",
        prompt_masked_text="What is [REDACTED]?",
        model_provider="ollama",
        model_name="mistral",
    )
    base.update(overrides)
    return base


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_returns_uuid(
    repo: RequestRepository, seeded_ids: dict[str, str]
):
    rid = await repo.create(**_make_request_kwargs(seeded_ids))
    assert isinstance(rid, str) and len(rid) == 36


@pytest.mark.asyncio
async def test_create_sets_status_pending(
    repo: RequestRepository, seeded_ids: dict[str, str], db_session: AsyncSession
):
    from sqlalchemy import select
    from sentinel.infrastructure.db.models import RequestORM

    rid = await repo.create(**_make_request_kwargs(seeded_ids))
    result = await db_session.execute(select(RequestORM).where(RequestORM.id == rid))
    row = result.scalar_one()
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_update_status_changes_value(
    repo: RequestRepository, seeded_ids: dict[str, str]
):
    from sqlalchemy import select
    from sentinel.infrastructure.db.models import RequestORM

    rid = await repo.create(**_make_request_kwargs(seeded_ids))
    await repo.update_status(rid, "processing")

    result = await repo._session.execute(
        select(RequestORM).where(RequestORM.id == rid)
    )
    row = result.scalar_one()
    assert row.status == "processing"


@pytest.mark.asyncio
async def test_update_completed_sets_all_fields(
    repo: RequestRepository, seeded_ids: dict[str, str]
):
    from sqlalchemy import select
    from sentinel.infrastructure.db.models import RequestORM

    rid = await repo.create(**_make_request_kwargs(seeded_ids))
    await repo.update_completed(
        rid,
        {
            "status": "completed",
            "guardrail_decision": "accept",
            "confidence_score": 85,
            "confidence_label": "high",
            "risk_score": 10,
            "total_latency_ms": 1200,
        },
    )

    result = await repo._session.execute(
        select(RequestORM).where(RequestORM.id == rid)
    )
    row = result.scalar_one()
    assert row.status == "completed"
    assert row.guardrail_decision == "accept"
    assert row.confidence_score == 85
    assert row.completed_at is not None


@pytest.mark.asyncio
async def test_list_by_session_returns_all(
    repo: RequestRepository, seeded_ids: dict[str, str]
):
    await repo.create(**_make_request_kwargs(seeded_ids, prompt_hash="h1"))
    await repo.create(**_make_request_kwargs(seeded_ids, prompt_hash="h2"))

    results = await repo.list_by_session(seeded_ids["session_id"])
    assert len(results) == 2
    assert all(isinstance(r, RequestSummary) for r in results)


@pytest.mark.asyncio
async def test_list_filter_by_decision_returns_only_matching(
    repo: RequestRepository, seeded_ids: dict[str, str]
):
    rid_block = await repo.create(**_make_request_kwargs(seeded_ids, prompt_hash="h1"))
    rid_accept = await repo.create(**_make_request_kwargs(seeded_ids, prompt_hash="h2"))

    await repo.update_completed(rid_block, {"status": "blocked", "guardrail_decision": "block"})
    await repo.update_completed(rid_accept, {"status": "completed", "guardrail_decision": "accept"})

    results = await repo.list_by_session(
        seeded_ids["session_id"],
        filters={"filter_by_decision": "block"},
    )
    assert len(results) == 1
    assert results[0].guardrail_decision == "block"


@pytest.mark.asyncio
async def test_list_filter_by_status(
    repo: RequestRepository, seeded_ids: dict[str, str]
):
    rid = await repo.create(**_make_request_kwargs(seeded_ids, prompt_hash="h1"))
    await repo.create(**_make_request_kwargs(seeded_ids, prompt_hash="h2"))
    await repo.update_status(rid, "processing")

    results = await repo.list_by_session(
        seeded_ids["session_id"],
        filters={"filter_by_status": "processing"},
    )
    assert len(results) == 1


@pytest.mark.asyncio
async def test_get_by_id_returns_request_detail(
    repo: RequestRepository, seeded_ids: dict[str, str]
):
    rid = await repo.create(**_make_request_kwargs(seeded_ids))
    detail = await repo.get_by_id(rid, seeded_ids["session_id"])

    assert detail is not None
    assert isinstance(detail, RequestDetail)
    assert detail.id == rid
    assert detail.pipeline_traces == []
    assert detail.request_claims == []
    assert detail.safety_filter_results == []


@pytest.mark.asyncio
async def test_get_by_id_wrong_session_returns_none(
    repo: RequestRepository, seeded_ids: dict[str, str]
):
    rid = await repo.create(**_make_request_kwargs(seeded_ids))
    result = await repo.get_by_id(rid, str(uuid.uuid4()))
    assert result is None


@pytest.mark.asyncio
async def test_get_by_id_loads_child_records(
    repo: RequestRepository,
    seeded_ids: dict[str, str],
    db_session: AsyncSession,
):
    """Verify selectinload fetches child records without N+1."""
    from sentinel.infrastructure.db.models import PipelineTraceORM, SafetyFilterResultORM
    from datetime import datetime, timezone

    rid = await repo.create(**_make_request_kwargs(seeded_ids))

    # Insert child records directly
    trace = PipelineTraceORM(
        id=str(uuid.uuid4()),
        request_id=rid,
        attempt_number=1,
        stage_order=1,
        stage_name="prompt_validation",
        stage_status="passed",
        stage_metadata="{}",
        created_at=datetime.now(timezone.utc),
    )
    safety = SafetyFilterResultORM(
        id=str(uuid.uuid4()),
        request_id=rid,
        attempt_number=1,
        filter_name="toxicity",
        result="clean",
        score=0.01,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(trace)
    db_session.add(safety)
    await db_session.commit()

    # Expire the session so the ORM re-fetches
    db_session.expire_all()

    detail = await repo.get_by_id(rid, seeded_ids["session_id"])
    assert detail is not None
    assert len(detail.pipeline_traces) == 1
    assert len(detail.safety_filter_results) == 1
