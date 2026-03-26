from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np  # type: ignore[import-not-found]

# Type aliases
type FloatArray = np.ndarray[Any, np.dtype[np.floating[Any]]]
type IntArray = np.ndarray[Any, np.dtype[np.integer[Any]]]


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for in-process vector index implementations.

    All mutating operations (add, remove_ids) must be concurrency-safe.
    Persistence is synchronous; callers are responsible for offloading to
    a thread pool if called from an async context that demands it.
    """

    async def add(self, vectors: FloatArray, ids: IntArray) -> None:
        """Add vectors with corresponding integer IDs to the index.

        Args:
            vectors: float32 array of shape (n, dimension). Will be L2-normalised
                     internally before insertion (caller's copy is not mutated).
            ids:     int64 array of shape (n,). Must be unique within the index.
        """
        ...

    async def query(self, vector: FloatArray, top_k: int) -> list[tuple[int, float]]:
        """Return the top-k nearest neighbours for a single query vector.

        Args:
            vector: float32 array of shape (dimension,) or (1, dimension).
            top_k:  maximum number of results to return.

        Returns:
            List of (faiss_id, similarity_score) tuples sorted by descending
            similarity score.  Returns [] when the index is empty.
        """
        ...

    async def remove_ids(self, ids: list[int]) -> None:
        """Remove vectors with the given IDs from the index.

        Args:
            ids: list of integer IDs previously passed to add().
        """
        ...

    def persist(self, path: Path) -> None:
        """Serialise the index to *path* on disk (synchronous).

        Args:
            path: destination file path (parent directory must exist).
        """
        ...

    def load(self, path: Path) -> None:
        """Deserialise an index from *path* into this instance (synchronous).

        Replaces the current in-memory index entirely.

        Args:
            path: path to a file previously written by persist().
        """
        ...
