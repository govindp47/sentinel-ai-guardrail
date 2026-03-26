from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np  # type: ignore[import-not-found]

# Type alias for float32 ndarray
type NDArray = np.ndarray[Any, np.dtype[np.floating[Any]]]


@runtime_checkable
class EmbeddingAdapter(Protocol):
    """Protocol for text-to-vector embedding implementations.

    All methods are async; implementations must dispatch CPU-bound model
    inference to a thread pool so the event loop is never blocked.
    """

    async def embed(self, text: str) -> NDArray:
        """Embed a single text string.

        Args:
            text: input text to embed.

        Returns:
            float32 ndarray of shape (embedding_dim,).
        """
        ...

    async def embed_batch(self, texts: list[str]) -> NDArray:
        """Embed a list of text strings in one batched call.

        Args:
            texts: list of input strings (must be non-empty).

        Returns:
            float32 ndarray of shape (len(texts), embedding_dim).
        """
        ...
