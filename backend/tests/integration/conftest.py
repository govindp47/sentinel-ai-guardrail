"""Shared fixtures for all infrastructure integration tests.

Available fixtures:
- ``async_test_db``:        migrated in-memory SQLite AsyncSession factory.
- ``faiss_store_256dim``:   empty FAISSStore with dimension=256.
- ``mock_embedding_adapter``: deterministic fake embeddings (no model loaded).
"""

from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import AsyncMock

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sentinel.infrastructure.vector_store.faiss_store import FAISSStore

# ---------------------------------------------------------------------------
# In-memory async SQLite session factory
# ---------------------------------------------------------------------------

_SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_test_db() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Yield an async session factory backed by a fresh in-memory SQLite DB.

    Tables are created via SQLAlchemy metadata reflection if models are
    imported.  Tests that need the schema should import the ORM models before
    calling this fixture so metadata is populated.
    """
    engine = create_async_engine(_SQLITE_URL, echo=False)

    # Import models so their metadata is registered before table creation.
    try:
        from sentinel.infrastructure.db import models as _models  # noqa: F401
        from sentinel.infrastructure.db.models import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except ImportError:
        # DB models not yet present in this phase — skip schema creation.
        pass

    factory = async_sessionmaker(engine, expire_on_commit=False)

    yield factory

    await engine.dispose()


# ---------------------------------------------------------------------------
# FAISS store fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def faiss_store_256dim() -> FAISSStore:
    """Return a fresh, empty FAISSStore with dimension=256."""
    return FAISSStore(dimension=256)


# ---------------------------------------------------------------------------
# Mock embedding adapter fixture
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(0)
_EMBED_DIM = 384


def _deterministic_embed(text: str) -> np.ndarray:
    """Return a deterministic float32 unit vector derived from *text*."""
    seed = abs(hash(text)) % (2**31)
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(_EMBED_DIM).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec


@pytest.fixture
def mock_embedding_adapter() -> AsyncMock:
    """Return an AsyncMock that satisfies the EmbeddingAdapter protocol.

    - ``embed(text)`` returns a deterministic unit vector of shape (384,).
    - ``embed_batch(texts)`` returns a deterministic array of shape (N, 384).

    No real model is loaded; suitable for use in tests that need embeddings
    without the 2-second SentenceTransformer load time.
    """
    adapter = AsyncMock()

    async def _embed(text: str) -> np.ndarray:
        return _deterministic_embed(text)

    async def _embed_batch(texts: list[str]) -> np.ndarray:
        return np.stack([_deterministic_embed(t) for t in texts])

    adapter.embed.side_effect = _embed
    adapter.embed_batch.side_effect = _embed_batch
    return adapter
