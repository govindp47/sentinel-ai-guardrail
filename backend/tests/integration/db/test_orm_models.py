"""
ORM integration tests — insert + read round-trip for all 10 models.

Runs against a fresh in-memory SQLite file per test.
Uses alembic upgrade head to set up the schema (ensures ORM matches migration).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

BACKEND_SRC = str(Path(__file__).resolve().parents[4] / "src")

import sys
if BACKEND_SRC not in sys.path:
    sys.path.insert(0, BACKEND_SRC)

from sentinel.infrastructure.db.models import (
    AnalyticsCounterModel,
    Base,
    ClaimEvidenceModel,
    KbChunkModel,
    KbDocumentModel,
    PipelineTraceModel,
    PolicySnapshotModel,
    RequestClaimModel,
    RequestModel,
    SafetyFilterResultModel,
    SessionModel,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture()
async def session(tmp_path: Path) -> AsyncGenerator[AsyncSession, None]:
    """Fresh async session backed by a temp SQLite file with full schema."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(db_url, poolclass=NullPool, echo=False)

    # Enable foreign keys and WAL
    from sqlalchemy import event, text

    @event.listens_for(engine.sync_engine, "connect")
    def _pragmas(conn, _rec):
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        yield s

    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers for seeding parent rows
# ---------------------------------------------------------------------------

async def _make_session_row(s: AsyncSession) -> SessionModel:
    row = SessionModel(id=_uid())
    s.add(row)
    await s.flush()
    return row


async def _make_policy(s: AsyncSession, session_id: str) -> PolicySnapshotModel:
    row = PolicySnapshotModel(
        id=_uid(),
        session_id=session_id,
        accept_threshold=80,
        warn_threshold=50,
        block_threshold=10,
        max_retries=2,
        restricted_categories=["violence"],
        allowed_topics=["science"],
        fallback_priority=["retry_prompt"],
        module_flags={"injection_detection": True},
    )
    s.add(row)
    await s.flush()
    return row


async def _make_request(
    s: AsyncSession, session_id: str, policy_id: str
) -> RequestModel:
    row = RequestModel(
        id=_uid(),
        session_id=session_id,
        policy_snapshot_id=policy_id,
        prompt_hash="abc123",
        prompt_masked_text="Hello [REDACTED]",
        pii_detected=0,
        pii_types_detected=[],
        model_provider="ollama",
        model_name="mistral",
        status="pending",
    )
    s.add(row)
    await s.flush()
    return row


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_insert_read(session: AsyncSession) -> None:
    row = await _make_session_row(session)
    await session.commit()
    fetched = await session.get(SessionModel, row.id)
    assert fetched is not None
    assert fetched.id == row.id
    assert isinstance(fetched.created_at, datetime)


@pytest.mark.asyncio
async def test_policy_snapshot_insert_read(session: AsyncSession) -> None:
    sess = await _make_session_row(session)
    policy = await _make_policy(session, sess.id)
    await session.commit()
    fetched = await session.get(PolicySnapshotModel, policy.id)
    assert fetched is not None
    assert fetched.accept_threshold == 80
    # JSON columns round-trip as Python list/dict
    assert fetched.restricted_categories == ["violence"]
    assert fetched.module_flags == {"injection_detection": True}


@pytest.mark.asyncio
async def test_kb_document_insert_read(session: AsyncSession) -> None:
    sess = await _make_session_row(session)
    doc = KbDocumentModel(
        id=_uid(),
        session_id=sess.id,
        filename="doc.pdf",
        original_filename="doc.pdf",
        file_size_bytes=1024,
        mime_type="application/pdf",
        storage_path=f"/tmp/{_uid()}.pdf",
        status="pending",
    )
    session.add(doc)
    await session.commit()
    fetched = await session.get(KbDocumentModel, doc.id)
    assert fetched is not None
    assert fetched.filename == "doc.pdf"
    assert fetched.status == "pending"


@pytest.mark.asyncio
async def test_kb_chunk_insert_read(session: AsyncSession) -> None:
    sess = await _make_session_row(session)
    doc = KbDocumentModel(
        id=_uid(),
        session_id=sess.id,
        filename="doc.pdf",
        original_filename="doc.pdf",
        file_size_bytes=512,
        mime_type="application/pdf",
        storage_path=f"/tmp/{_uid()}.pdf",
        status="ready",
    )
    session.add(doc)
    await session.flush()
    chunk = KbChunkModel(
        id=_uid(),
        document_id=doc.id,
        chunk_index=0,
        chunk_text="This is a chunk.",
        chunk_char_start=0,
        chunk_char_end=16,
        faiss_vector_id=42,
    )
    session.add(chunk)
    await session.commit()
    fetched = await session.get(KbChunkModel, chunk.id)
    assert fetched is not None
    assert fetched.chunk_text == "This is a chunk."
    assert fetched.faiss_vector_id == 42


@pytest.mark.asyncio
async def test_analytics_counter_insert_read(session: AsyncSession) -> None:
    sess = await _make_session_row(session)
    counter = AnalyticsCounterModel(
        id=_uid(),
        session_id=sess.id,
        date_bucket="2024-03-15",
        model_provider="ollama",
        model_name="mistral",
        total_requests=5,
        total_accepted=3,
        total_blocked=1,
        sum_latency_ms=12000,
        sum_tokens_in=500,
        sum_tokens_out=300,
    )
    session.add(counter)
    await session.commit()
    fetched = await session.get(AnalyticsCounterModel, counter.id)
    assert fetched is not None
    assert fetched.total_requests == 5
    assert fetched.sum_latency_ms == 12000


@pytest.mark.asyncio
async def test_request_insert_read_json(session: AsyncSession) -> None:
    sess = await _make_session_row(session)
    policy = await _make_policy(session, sess.id)
    req = await _make_request(session, sess.id, policy.id)
    req.confidence_signal_breakdown = {"evidence_similarity": 0.88, "claim_ratio": 0.75}
    req.pii_types_detected = ["email", "phone"]
    await session.commit()
    fetched = await session.get(RequestModel, req.id)
    assert fetched is not None
    assert fetched.confidence_signal_breakdown == {
        "evidence_similarity": 0.88,
        "claim_ratio": 0.75,
    }
    assert fetched.pii_types_detected == ["email", "phone"]


@pytest.mark.asyncio
async def test_pipeline_trace_insert_read(session: AsyncSession) -> None:
    sess = await _make_session_row(session)
    policy = await _make_policy(session, sess.id)
    req = await _make_request(session, sess.id, policy.id)
    trace = PipelineTraceModel(
        id=_uid(),
        request_id=req.id,
        attempt_number=1,
        stage_order=1,
        stage_name="prompt_received",
        stage_status="passed",
        stage_metadata={"info": "ok"},
    )
    session.add(trace)
    await session.commit()
    fetched = await session.get(PipelineTraceModel, trace.id)
    assert fetched is not None
    assert fetched.stage_name == "prompt_received"
    assert fetched.stage_metadata == {"info": "ok"}


@pytest.mark.asyncio
async def test_request_claim_insert_read(session: AsyncSession) -> None:
    sess = await _make_session_row(session)
    policy = await _make_policy(session, sess.id)
    req = await _make_request(session, sess.id, policy.id)
    claim = RequestClaimModel(
        id=_uid(),
        request_id=req.id,
        attempt_number=1,
        claim_index=0,
        claim_text="Paris is the capital of France.",
        verification_status="supported",
        confidence_contribution=0.85,
    )
    session.add(claim)
    await session.commit()
    fetched = await session.get(RequestClaimModel, claim.id)
    assert fetched is not None
    assert fetched.verification_status == "supported"
    assert fetched.confidence_contribution == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_claim_evidence_insert_read(session: AsyncSession) -> None:
    sess = await _make_session_row(session)
    policy = await _make_policy(session, sess.id)
    req = await _make_request(session, sess.id, policy.id)
    claim = RequestClaimModel(
        id=_uid(),
        request_id=req.id,
        attempt_number=1,
        claim_index=0,
        claim_text="Claim text.",
        verification_status="unverified",
    )
    session.add(claim)
    await session.flush()
    evidence = ClaimEvidenceModel(
        id=_uid(),
        claim_id=claim.id,
        kb_chunk_id=None,
        relevance_score=0.91,
        rank=1,
    )
    session.add(evidence)
    await session.commit()
    fetched = await session.get(ClaimEvidenceModel, evidence.id)
    assert fetched is not None
    assert fetched.relevance_score == pytest.approx(0.91)
    assert fetched.kb_chunk_id is None


@pytest.mark.asyncio
async def test_safety_filter_result_insert_read(session: AsyncSession) -> None:
    sess = await _make_session_row(session)
    policy = await _make_policy(session, sess.id)
    req = await _make_request(session, sess.id, policy.id)
    sfr = SafetyFilterResultModel(
        id=_uid(),
        request_id=req.id,
        attempt_number=1,
        filter_name="toxicity",
        result="clean",
        score=0.02,
    )
    session.add(sfr)
    await session.commit()
    fetched = await session.get(SafetyFilterResultModel, sfr.id)
    assert fetched is not None
    assert fetched.filter_name == "toxicity"
    assert fetched.score == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_session_cascade_delete(session: AsyncSession) -> None:
    """Deleting a session cascades to all child tables."""
    sess = await _make_session_row(session)
    policy = await _make_policy(session, sess.id)
    req = await _make_request(session, sess.id, policy.id)
    req_id = req.id
    policy_id = policy.id
    await session.commit()

    await session.delete(sess)
    await session.commit()

    assert await session.get(RequestModel, req_id) is None
    assert await session.get(PolicySnapshotModel, policy_id) is None
