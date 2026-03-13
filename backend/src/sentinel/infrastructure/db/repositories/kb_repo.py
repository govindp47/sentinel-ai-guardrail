"""
KBRepository — interface Protocol + NotImplementedError stub.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.infrastructure.db.repositories.base import BaseRepository


class KbDocumentRow:
    """Placeholder carrier."""

    ...


class KbChunkRow:
    """Placeholder carrier."""

    ...


@runtime_checkable
class KBRepositoryProtocol(Protocol):
    async def create_document(
        self,
        *,
        id: str,
        session_id: str,
        filename: str,
        original_filename: str,
        file_size_bytes: int,
        mime_type: str,
        storage_path: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> KbDocumentRow: ...

    async def update_document_status(
        self,
        document_id: str,
        *,
        status: str,
        chunk_count: int | None = None,
        indexed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None: ...

    async def get_document(
        self,
        document_id: str,
        session_id: str,
    ) -> KbDocumentRow | None: ...

    async def list_documents_by_session(
        self,
        session_id: str,
    ) -> list[KbDocumentRow]: ...

    async def delete_document(
        self,
        document_id: str,
        session_id: str,
    ) -> None: ...

    async def create_chunk(
        self,
        *,
        id: str,
        document_id: str,
        chunk_index: int,
        chunk_text: str,
        chunk_char_start: int,
        chunk_char_end: int,
        token_count: int | None,
    ) -> KbChunkRow: ...

    async def update_chunk_faiss_id(
        self,
        chunk_id: str,
        faiss_vector_id: int,
    ) -> None: ...

    async def get_chunks_by_document(
        self,
        document_id: str,
    ) -> list[KbChunkRow]: ...

    async def get_chunk_by_faiss_id(
        self,
        faiss_vector_id: int,
        session_id: str,
    ) -> KbChunkRow | None: ...

    async def get_chunks_by_faiss_ids(
        self,
        faiss_vector_ids: list[int],
        session_id: str,
    ) -> list[KbChunkRow]: ...


class KBRepository(BaseRepository):
    """Stub implementation — all methods raise NotImplementedError (Phase 1)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create_document(
        self,
        *,
        id: str,
        session_id: str,
        filename: str,
        original_filename: str,
        file_size_bytes: int,
        mime_type: str,
        storage_path: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> KbDocumentRow:
        raise NotImplementedError

    async def update_document_status(
        self,
        document_id: str,
        *,
        status: str,
        chunk_count: int | None = None,
        indexed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        raise NotImplementedError

    async def get_document(
        self,
        document_id: str,
        session_id: str,
    ) -> KbDocumentRow | None:
        raise NotImplementedError

    async def list_documents_by_session(
        self,
        session_id: str,
    ) -> list[KbDocumentRow]:
        raise NotImplementedError

    async def delete_document(
        self,
        document_id: str,
        session_id: str,
    ) -> None:
        raise NotImplementedError

    async def create_chunk(
        self,
        *,
        id: str,
        document_id: str,
        chunk_index: int,
        chunk_text: str,
        chunk_char_start: int,
        chunk_char_end: int,
        token_count: int | None,
    ) -> KbChunkRow:
        raise NotImplementedError

    async def update_chunk_faiss_id(
        self,
        chunk_id: str,
        faiss_vector_id: int,
    ) -> None:
        raise NotImplementedError

    async def get_chunks_by_document(
        self,
        document_id: str,
    ) -> list[KbChunkRow]:
        raise NotImplementedError

    async def get_chunk_by_faiss_id(
        self,
        faiss_vector_id: int,
        session_id: str,
    ) -> KbChunkRow | None:
        raise NotImplementedError

    async def get_chunks_by_faiss_ids(
        self,
        faiss_vector_ids: list[int],
        session_id: str,
    ) -> list[KbChunkRow]:
        raise NotImplementedError
