from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.infrastructure.db.models import KbChunkORM, KbDocumentORM

# ── Lightweight read model ────────────────────────────────────────────────────


@dataclass
class KBChunk:
    id: str
    document_id: str
    chunk_index: int
    chunk_text: str
    chunk_char_start: int
    chunk_char_end: int
    faiss_vector_id: int | None
    token_count: int | None
    created_at: datetime


# ── Repository ────────────────────────────────────────────────────────────────


class KBRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_document(
        self,
        session_id: str,
        filename: str,
        original_filename: str,
        file_size: int,
        mime_type: str,
        storage_path: str,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> str:
        """Insert a new KB document with status='pending'. Returns the new UUID."""
        doc_id = str(uuid.uuid4())
        row = KbDocumentORM(
            id=doc_id,
            session_id=session_id,
            filename=filename,
            original_filename=original_filename,
            file_size_bytes=file_size,
            mime_type=mime_type,
            storage_path=storage_path,
            status="pending",
            chunk_count=0,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.commit()
        return doc_id

    async def update_document_status(
        self,
        document_id: str,
        status: str,
        chunk_count: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """
        Update document status. Optionally sets chunk_count and error_message.
        When status='ready', also sets indexed_at to now.
        """
        values: dict[str, Any] = {"status": status}
        if chunk_count is not None:
            values["chunk_count"] = chunk_count
        if error_message is not None:
            values["error_message"] = error_message
        if status == "ready":
            values["indexed_at"] = datetime.now(UTC)

        stmt = update(KbDocumentORM).where(KbDocumentORM.id == document_id).values(**values)
        await self._session.execute(stmt)
        await self._session.commit()

    async def create_chunk(
        self,
        document_id: str,
        chunk_index: int,
        chunk_text: str,
        char_start: int,
        char_end: int,
        faiss_vector_id: int | None = None,
        token_count: int | None = None,
    ) -> str:
        """Insert a single KB chunk. Returns the new UUID."""
        chunk_id = str(uuid.uuid4())
        row = KbChunkORM(
            id=chunk_id,
            document_id=document_id,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            chunk_char_start=char_start,
            chunk_char_end=char_end,
            faiss_vector_id=faiss_vector_id,
            token_count=token_count,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.commit()
        return chunk_id

    async def get_chunks_by_document(self, document_id: str) -> list[KBChunk]:
        """Return all chunks for a document ordered by chunk_index."""
        result = await self._session.execute(
            select(KbChunkORM)
            .where(KbChunkORM.document_id == document_id)
            .order_by(KbChunkORM.chunk_index)
        )
        rows = result.scalars().all()
        return [_orm_to_chunk(r) for r in rows]

    async def get_chunk_by_faiss_id(self, faiss_id: int) -> KBChunk | None:
        """Reverse lookup: FAISS vector ID → KBChunk. Returns None if not found."""
        result = await self._session.execute(
            select(KbChunkORM).where(KbChunkORM.faiss_vector_id == faiss_id)
        )
        row: KbChunkORM | None = result.scalar_one_or_none()
        if row is None:
            return None
        return _orm_to_chunk(row)


def _orm_to_chunk(row: KbChunkORM) -> KBChunk:
    return KBChunk(
        id=row.id,
        document_id=row.document_id,
        chunk_index=row.chunk_index,
        chunk_text=row.chunk_text,
        chunk_char_start=row.chunk_char_start,
        chunk_char_end=row.chunk_char_end,
        faiss_vector_id=row.faiss_vector_id,
        token_count=row.token_count,
        created_at=row.created_at,
    )
