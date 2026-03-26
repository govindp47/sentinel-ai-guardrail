"""Integration tests for FAISSStore.

Covers:
- add → query round-trip (top-k ordering)
- add → remove → query (removed vector absent)
- persist → load → query (identical results)
- empty index query (returns [])
- concurrent add (no corruption)
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import numpy as np
import pytest

from sentinel.infrastructure.vector_store.faiss_store import FAISSStore

pytestmark = pytest.mark.faiss

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DIMENSION = 64
RNG = np.random.default_rng(42)


def _random_vectors(n: int, dim: int = DIMENSION) -> np.ndarray:
    """Return L2-normalised random float32 vectors of shape (n, dim)."""
    vecs = RNG.standard_normal((n, dim)).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / norms


def _ids(start: int, n: int) -> np.ndarray:
    return np.arange(start, start + n, dtype=np.int64)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEmptyIndex:
    @pytest.mark.asyncio
    async def test_query_empty_returns_empty_list(self) -> None:
        store = FAISSStore(dimension=DIMENSION)
        result = await store.query(_random_vectors(1)[0], top_k=5)
        assert result == []


class TestAddAndQuery:
    @pytest.mark.asyncio
    async def test_top_k_returns_correct_count(self) -> None:
        store = FAISSStore(dimension=DIMENSION)
        vecs = _random_vectors(10)
        await store.add(vecs, _ids(0, 10))

        results = await store.query(vecs[0], top_k=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_results_sorted_descending(self) -> None:
        store = FAISSStore(dimension=DIMENSION)
        vecs = _random_vectors(10)
        await store.add(vecs, _ids(0, 10))

        results = await store.query(_random_vectors(1)[0], top_k=5)
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_exact_match_is_top_result(self) -> None:
        """Querying with a stored vector should return that vector as #1."""
        store = FAISSStore(dimension=DIMENSION)
        vecs = _random_vectors(10)
        await store.add(vecs, _ids(0, 10))

        results = await store.query(vecs[3], top_k=1)
        assert len(results) == 1
        top_id, top_score = results[0]
        assert top_id == 3
        assert top_score == pytest.approx(1.0, abs=1e-5)

    @pytest.mark.asyncio
    async def test_top_k_larger_than_index_returns_all(self) -> None:
        store = FAISSStore(dimension=DIMENSION)
        vecs = _random_vectors(5)
        await store.add(vecs, _ids(0, 5))

        results = await store.query(vecs[0], top_k=100)
        assert len(results) == 5


class TestRemove:
    @pytest.mark.asyncio
    async def test_removed_id_not_in_query_results(self) -> None:
        store = FAISSStore(dimension=DIMENSION)
        vecs = _random_vectors(10)
        await store.add(vecs, _ids(0, 10))

        # Remove vector at index 3
        await store.remove_ids([3])

        # Query with the removed vector itself — it must not appear
        results = await store.query(vecs[3], top_k=10)
        returned_ids = {rid for rid, _ in results}
        assert 3 not in returned_ids

    @pytest.mark.asyncio
    async def test_ntotal_decreases_after_remove(self) -> None:
        store = FAISSStore(dimension=DIMENSION)
        vecs = _random_vectors(10)
        await store.add(vecs, _ids(0, 10))
        assert store.ntotal == 10

        await store.remove_ids([0, 1, 2])
        assert store.ntotal == 7

    @pytest.mark.asyncio
    async def test_query_after_full_remove_returns_empty(self) -> None:
        store = FAISSStore(dimension=DIMENSION)
        vecs = _random_vectors(5)
        await store.add(vecs, _ids(0, 5))
        await store.remove_ids(list(range(5)))

        results = await store.query(vecs[0], top_k=5)
        assert results == []


class TestPersistence:
    @pytest.mark.asyncio
    async def test_persist_and_load_returns_identical_results(self) -> None:
        store = FAISSStore(dimension=DIMENSION)
        vecs = _random_vectors(10)
        await store.add(vecs, _ids(0, 10))

        query_vec = _random_vectors(1)[0]
        results_before = await store.query(query_vec, top_k=5)

        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "test.faiss"
            store.persist(index_path)

            store2 = FAISSStore(dimension=DIMENSION)
            store2.load(index_path)

        results_after = await store2.query(query_vec, top_k=5)

        assert len(results_before) == len(results_after)
        for (id_before, score_before), (id_after, score_after) in zip(
            results_before, results_after
        ):
            assert id_before == id_after
            assert score_before == pytest.approx(score_after, abs=1e-5)

    @pytest.mark.asyncio
    async def test_persist_preserves_ntotal(self) -> None:
        store = FAISSStore(dimension=DIMENSION)
        vecs = _random_vectors(7)
        await store.add(vecs, _ids(0, 7))

        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "test.faiss"
            store.persist(index_path)

            store2 = FAISSStore(dimension=DIMENSION)
            store2.load(index_path)

        assert store2.ntotal == 7


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_add_no_corruption(self) -> None:
        """Two concurrent tasks adding 50 vectors each must not corrupt the index."""
        store = FAISSStore(dimension=DIMENSION)

        async def add_batch(start: int) -> None:
            vecs = _random_vectors(50)
            await store.add(vecs, _ids(start, 50))

        await asyncio.gather(add_batch(0), add_batch(50))

        assert store.ntotal == 100

        # Index must be queryable without error
        results = await store.query(_random_vectors(1)[0], top_k=10)
        assert len(results) == 10
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_concurrent_add_and_remove(self) -> None:
        """Interleaved add and remove must not crash or corrupt results."""
        store = FAISSStore(dimension=DIMENSION)
        seed_vecs = _random_vectors(20)
        await store.add(seed_vecs, _ids(0, 20))

        async def add_more() -> None:
            vecs = _random_vectors(10)
            await store.add(vecs, _ids(100, 10))

        async def remove_some() -> None:
            await store.remove_ids([0, 1, 2, 3, 4])

        await asyncio.gather(add_more(), remove_some())

        # 20 initial − 5 removed + 10 added = 25
        assert store.ntotal == 25

        # Removed IDs must not appear
        results = await store.query(_random_vectors(1)[0], top_k=25)
        returned_ids = {rid for rid, _ in results}
        for removed_id in [0, 1, 2, 3, 4]:
            assert removed_id not in returned_ids


class TestDimensionValidation:
    @pytest.mark.asyncio
    async def test_wrong_dimension_on_add_raises(self) -> None:
        store = FAISSStore(dimension=DIMENSION)
        wrong_vecs = _random_vectors(3, dim=DIMENSION + 1)
        with pytest.raises(ValueError, match="dimension"):
            await store.add(wrong_vecs, _ids(0, 3))

    @pytest.mark.asyncio
    async def test_wrong_dimension_on_query_raises(self) -> None:
        store = FAISSStore(dimension=DIMENSION)
        vecs = _random_vectors(5)
        await store.add(vecs, _ids(0, 5))

        wrong_query = _random_vectors(1, dim=DIMENSION + 1)[0]
        with pytest.raises(ValueError, match="dimension"):
            await store.query(wrong_query, top_k=3)

    def test_non_positive_dimension_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            FAISSStore(dimension=0)
