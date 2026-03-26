from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from sentinel.infrastructure.db.models import Base
from sentinel.infrastructure.db.repositories.kb_repo import KBChunk, KBRepository
from sentinel.infrastructure.db.repositories.session_repo import SessionRepository


# ── Fixtures ──────────────────────────────────────────────────────────────────


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
async def session_id(db_session: AsyncSession) -> str:
    sid = str(uuid.uuid4())
    await SessionRepository(db_session).create_or_get(sid)
    return sid


@pytest_asyncio.fixture()
async def repo(db_session: AsyncSession):
    return KBRepository(db_session)


async def _create_doc(
    repo: KBRepository, session_id: str, storage_path: str | None = None
) -> str:
    return await repo.create_document(
        session_id=session_id,
        filename="test.pdf",
        original_filename="test.pdf",
        file_size=1024,
        mime_type="application/pdf",
        storage_path=storage_path or f"/uploads/{uuid.uuid4()}.pdf",
    )


# ── Tests: document lifecycle ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_document_returns_uuid(
    repo: KBRepository, session_id: str
):
    doc_id = await _create_doc(repo, session_id)
    assert isinstance(doc_id, str) and len(doc_id) == 36


@pytest.mark.asyncio
async def test_create_document_sets_status_pending(
    repo: KBRepository, session_id: str, db_session: AsyncSession
):
    from sqlalchemy import select
    from sentinel.infrastructure.db.models import Base, KbDocumentORM

    doc_id = await _create_doc(repo, session_id)
    result = await db_session.execute(
        select(KbDocumentORM).where(KbDocumentORM.id == doc_id)
    )
    row = result.scalar_one()
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_update_document_status_lifecycle(
    repo: KBRepository, session_id: str, db_session: AsyncSession
):
    from sqlalchemy import select
    from sentinel.infrastructure.db.models import Base, KbDocumentORM

    doc_id = await _create_doc(repo, session_id)

    await repo.update_document_status(doc_id, "indexing")
    result = await db_session.execute(
        select(KbDocumentORM).where(KbDocumentORM.id == doc_id)
    )
    db_session.expire_all()
    result = await db_session.execute(
        select(KbDocumentORM).where(KbDocumentORM.id == doc_id)
    )
    row = result.scalar_one()
    assert row.status == "indexing"

    await repo.update_document_status(doc_id, "ready", chunk_count=5)
    db_session.expire_all()
    result = await db_session.execute(
        select(KbDocumentORM).where(KbDocumentORM.id == doc_id)
    )
    row = result.scalar_one()
    assert row.status == "ready"
    assert row.chunk_count == 5
    assert row.indexed_at is not None


@pytest.mark.asyncio
async def test_update_document_status_failed_sets_error_message(
    repo: KBRepository, session_id: str, db_session: AsyncSession
):
    from sqlalchemy import select
    from sentinel.infrastructure.db.models import KbDocumentORM

    doc_id = await _create_doc(repo, session_id)
    await repo.update_document_status(
        doc_id, "failed", error_message="Embedding service unavailable"
    )
    db_session.expire_all()
    result = await db_session.execute(
        select(KbDocumentORM).where(KbDocumentORM.id == doc_id)
    )
    row = result.scalar_one()
    assert row.status == "failed"
    assert row.error_message == "Embedding service unavailable"


# ── Tests: chunk insertion and retrieval ──────────────────────────────────────


@pytest.mark.asyncio
async def test_create_chunk_returns_uuid(
    repo: KBRepository, session_id: str
):
    doc_id = await _create_doc(repo, session_id)
    chunk_id = await repo.create_chunk(
        document_id=doc_id,
        chunk_index=0,
        chunk_text="Hello world chunk",
        char_start=0,
        char_end=17,
        faiss_vector_id=42,
    )
    assert isinstance(chunk_id, str) and len(chunk_id) == 36


@pytest.mark.asyncio
async def test_get_chunks_by_document_ordered(
    repo: KBRepository, session_id: str
):
    doc_id = await _create_doc(repo, session_id)
    for i in range(3):
        await repo.create_chunk(
            document_id=doc_id,
            chunk_index=i,
            chunk_text=f"chunk {i}",
            char_start=i * 10,
            char_end=i * 10 + 7,
        )

    chunks = await repo.get_chunks_by_document(doc_id)
    assert len(chunks) == 3
    assert [c.chunk_index for c in chunks] == [0, 1, 2]
    assert all(isinstance(c, KBChunk) for c in chunks)


@pytest.mark.asyncio
async def test_get_chunks_by_document_empty(
    repo: KBRepository, session_id: str
):
    doc_id = await _create_doc(repo, session_id)
    chunks = await repo.get_chunks_by_document(doc_id)
    assert chunks == []


@pytest.mark.asyncio
async def test_get_chunk_by_faiss_id(
    repo: KBRepository, session_id: str
):
    doc_id = await _create_doc(repo, session_id)
    await repo.create_chunk(
        document_id=doc_id,
        chunk_index=0,
        chunk_text="The quick brown fox",
        char_start=0,
        char_end=19,
        faiss_vector_id=777,
    )

    chunk = await repo.get_chunk_by_faiss_id(777)
    assert chunk is not None
    assert chunk.chunk_text == "The quick brown fox"
    assert chunk.faiss_vector_id == 777


@pytest.mark.asyncio
async def test_get_chunk_by_faiss_id_not_found(
    repo: KBRepository, session_id: str
):
    chunk = await repo.get_chunk_by_faiss_id(99999)
    assert chunk is None
