from __future__ import annotations

import asyncio
import functools
from typing import Any, cast

from cachetools import LRUCache
import numpy as np
from sentence_transformers import SentenceTransformer

# Type alias for float32 ndarray
type NDArray = np.ndarray[Any, np.dtype[np.floating[Any]]]


class SentenceTransformerAdapter:
    """Async embedding adapter wrapping a SentenceTransformer model.

    Single-text embeddings are LRU-cached to avoid redundant inference.
    Both embed() and embed_batch() dispatch model.encode() to the default
    thread-pool executor so the asyncio event loop is never blocked.

    Cache access is serialised by an asyncio.Lock — this prevents a
    cache-stampede where two concurrent coroutines both miss the cache for
    the same key and both trigger inference.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        cache_size: int = 512,
    ) -> None:
        """Load the model and initialise the LRU cache.

        Args:
            model_name:  HuggingFace model identifier passed to
                         SentenceTransformer (default: all-MiniLM-L6-v2).
            cache_size:  maximum number of single-text embeddings to cache.
        """
        self._model: SentenceTransformer = SentenceTransformer(model_name)
        self._cache: LRUCache[str, NDArray] = LRUCache(maxsize=cache_size)
        self._cache_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # EmbeddingAdapter protocol implementation
    # ------------------------------------------------------------------

    async def embed(self, text: str) -> NDArray:
        """Return a float32 embedding of shape (embedding_dim,).

        Cache hit: returns the stored array immediately (no model call).
        Cache miss: dispatches model.encode to the thread pool, stores result.

        Args:
            text: input string to embed.

        Returns:
            float32 ndarray of shape (embedding_dim,).
        """
        async with self._cache_lock:
            cached: NDArray | None = self._cache.get(text)
            if cached is not None:
                return cached

        # Release the lock before the blocking call so other coroutines
        # can serve their own cache hits while inference runs.
        vector = await self._run_encode([text], batch_size=1)
        result: NDArray = cast(NDArray, vector[0])

        async with self._cache_lock:
            self._cache[text] = result

        return result

    async def embed_batch(self, texts: list[str]) -> NDArray:
        """Return float32 embeddings of shape (len(texts), embedding_dim).

        Bypasses the single-item cache intentionally — batch callers manage
        their own caching at a higher layer if needed.

        Args:
            texts: list of strings to embed (must be non-empty).

        Returns:
            float32 ndarray of shape (len(texts), embedding_dim).
        """
        if not texts:
            raise ValueError("embed_batch requires at least one text")
        return await self._run_encode(texts, batch_size=32)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_encode(self, texts: list[str], batch_size: int) -> NDArray:
        """Dispatch model.encode to the default thread-pool executor.

        Args:
            texts:      list of strings to encode.
            batch_size: batch size forwarded to model.encode.

        Returns:
            float32 ndarray of shape (len(texts), embedding_dim).
        """
        loop = asyncio.get_event_loop()
        encode_fn = functools.partial(
            self._model.encode,
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=False,
        )
        result: Any = await loop.run_in_executor(None, encode_fn)
        return cast(NDArray, np.asarray(result, dtype=np.float32))

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def cache_info(self) -> dict[str, int]:
        """Return current LRU cache hit/miss counters and size."""
        return {
            "currsize": int(self._cache.currsize),
            "maxsize": int(self._cache.maxsize),
        }
