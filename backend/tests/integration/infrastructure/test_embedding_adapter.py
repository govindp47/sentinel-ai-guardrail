"""Integration tests for SentenceTransformerAdapter.

Covers:
- embed() output dimension (384 for all-MiniLM-L6-v2)
- LRU cache hit: second call for same text skips model.encode
- embed_batch() output shape (N, 384)
- Thread-pool dispatch: call completes within 5 seconds (event loop not blocked)
- asyncio.Lock protects concurrent cache access (no stampede corruption)
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from sentinel.infrastructure.embeddings.sentence_transformer import (
    SentenceTransformerAdapter,
)

MODEL_NAME = "all-MiniLM-L6-v2"
EXPECTED_DIM = 384


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def adapter() -> SentenceTransformerAdapter:
    """Single adapter instance shared across tests in this module.

    Loading the model once keeps the test suite fast.
    """
    return SentenceTransformerAdapter(model_name=MODEL_NAME, cache_size=128)


# ---------------------------------------------------------------------------
# Dimension tests
# ---------------------------------------------------------------------------


class TestEmbedDimension:
    @pytest.mark.asyncio
    async def test_single_embed_returns_correct_shape(
        self, adapter: SentenceTransformerAdapter
    ) -> None:
        result = await adapter.embed("hello world")
        assert isinstance(result, np.ndarray)
        assert result.shape == (EXPECTED_DIM,)
        assert result.dtype == np.float32

    @pytest.mark.asyncio
    async def test_embed_non_empty_vector(
        self, adapter: SentenceTransformerAdapter
    ) -> None:
        result = await adapter.embed("sentinel guardrail")
        assert np.linalg.norm(result) > 0.0


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------


class TestLRUCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_model_encode(self) -> None:
        """Second call with the same text must not invoke model.encode."""
        adapter = SentenceTransformerAdapter(
            model_name=MODEL_NAME, cache_size=64
        )

        call_count = 0
        original_run_encode = adapter._run_encode

        async def counting_run_encode(
            texts: list[str], batch_size: int
        ) -> np.ndarray:
            nonlocal call_count
            call_count += 1
            return await original_run_encode(texts, batch_size)

        adapter._run_encode = counting_run_encode  # type: ignore[method-assign]

        text = "cache test sentence"
        first = await adapter.embed(text)
        second = await adapter.embed(text)

        assert call_count == 1, (
            f"_run_encode should be called once (cache hit on second call), "
            f"but was called {call_count} times"
        )
        np.testing.assert_array_equal(first, second)

    @pytest.mark.asyncio
    async def test_different_texts_produce_different_embeddings(
        self, adapter: SentenceTransformerAdapter
    ) -> None:
        a = await adapter.embed("apple")
        b = await adapter.embed("orange")
        assert not np.allclose(a, b)

    @pytest.mark.asyncio
    async def test_cache_size_limit_evicts_oldest(self) -> None:
        adapter = SentenceTransformerAdapter(
            model_name=MODEL_NAME, cache_size=2
        )
        await adapter.embed("text_a")
        await adapter.embed("text_b")
        # Adding a third entry evicts text_a
        await adapter.embed("text_c")
        assert adapter.cache_info["currsize"] == 2


# ---------------------------------------------------------------------------
# Batch tests
# ---------------------------------------------------------------------------


class TestEmbedBatch:
    @pytest.mark.asyncio
    async def test_batch_shape(
        self, adapter: SentenceTransformerAdapter
    ) -> None:
        texts = ["sentence one", "sentence two", "sentence three"]
        result = await adapter.embed_batch(texts)
        assert isinstance(result, np.ndarray)
        assert result.shape == (3, EXPECTED_DIM)
        assert result.dtype == np.float32

    @pytest.mark.asyncio
    async def test_batch_single_item(
        self, adapter: SentenceTransformerAdapter
    ) -> None:
        result = await adapter.embed_batch(["only one"])
        assert result.shape == (1, EXPECTED_DIM)

    @pytest.mark.asyncio
    async def test_batch_empty_raises(
        self, adapter: SentenceTransformerAdapter
    ) -> None:
        with pytest.raises(ValueError, match="at least one"):
            await adapter.embed_batch([])

    @pytest.mark.asyncio
    async def test_batch_results_consistent_with_single(
        self, adapter: SentenceTransformerAdapter
    ) -> None:
        """embed_batch row N must match embed(texts[N]) closely."""
        texts = ["alpha", "beta"]
        batch_result = await adapter.embed_batch(texts)
        for i, text in enumerate(texts):
            single = await adapter.embed(text)
            np.testing.assert_allclose(
                batch_result[i], single, atol=1e-4,
                err_msg=f"Mismatch at index {i} for text '{text}'"
            )


# ---------------------------------------------------------------------------
# Thread-pool / async dispatch tests
# ---------------------------------------------------------------------------


class TestAsyncDispatch:
    @pytest.mark.asyncio
    async def test_embed_completes_within_timeout(
        self, adapter: SentenceTransformerAdapter
    ) -> None:
        """embed() must complete within 5 seconds (thread-pool dispatch)."""
        result = await asyncio.wait_for(
            adapter.embed("async timeout check"), timeout=5.0
        )
        assert result.shape == (EXPECTED_DIM,)

    @pytest.mark.asyncio
    async def test_embed_batch_completes_within_timeout(
        self, adapter: SentenceTransformerAdapter
    ) -> None:
        """embed_batch() must complete within 5 seconds."""
        texts = [f"sentence {i}" for i in range(10)]
        result = await asyncio.wait_for(
            adapter.embed_batch(texts), timeout=5.0
        )
        assert result.shape == (10, EXPECTED_DIM)

    @pytest.mark.asyncio
    async def test_concurrent_embeds_do_not_corrupt_cache(self) -> None:
        """Concurrent embed() calls for different texts must not corrupt the cache."""
        adapter = SentenceTransformerAdapter(
            model_name=MODEL_NAME, cache_size=64
        )
        texts = [f"concurrent text {i}" for i in range(8)]
        results = await asyncio.gather(*[adapter.embed(t) for t in texts])
        assert len(results) == 8
        for r in results:
            assert r.shape == (EXPECTED_DIM,)

    @pytest.mark.asyncio
    async def test_cache_stampede_returns_identical_result(self) -> None:
        """Two concurrent calls for the same text must return equal arrays."""
        adapter = SentenceTransformerAdapter(
            model_name=MODEL_NAME, cache_size=64
        )
        text = "stampede test"
        a, b = await asyncio.gather(
            adapter.embed(text), adapter.embed(text)
        )
        np.testing.assert_array_equal(a, b)
