from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import faiss  # type: ignore[import-untyped]
import numpy as np

# Type aliases
type FloatArray = np.ndarray[Any, np.dtype[np.floating[Any]]]
type IntArray = np.ndarray[Any, np.dtype[np.integer[Any]]]


class FAISSStore:
    """In-process FAISS vector store backed by IndexIDMap(IndexFlatIP).

    Vectors are L2-normalised before insertion so that inner-product search
    is equivalent to cosine similarity.

    Each instance owns exactly one FAISS index and one asyncio.Lock that
    serialises all mutating operations (add, remove_ids).  Read operations
    (query) do not acquire the lock because FAISS search is thread-safe for
    simultaneous reads when no write is in progress; however, because all
    callers share a single asyncio event loop, the lock is sufficient to
    prevent concurrent reads and writes.
    """

    def __init__(self, dimension: int) -> None:
        """Initialise an empty index.

        Args:
            dimension: embedding vector dimensionality (e.g. 384 for MiniLM).
        """
        if dimension <= 0:
            raise ValueError(f"dimension must be positive, got {dimension}")

        self._dimension: int = dimension
        self._index: faiss.IndexIDMap = faiss.IndexIDMap(faiss.IndexFlatIP(dimension))
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_float32_2d(arr: FloatArray) -> FloatArray:
        """Return a C-contiguous float32 copy with ndim == 2."""
        arr = np.array(arr, dtype=np.float32, copy=True)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if not arr.flags["C_CONTIGUOUS"]:
            arr = np.ascontiguousarray(arr)
        return arr

    @staticmethod
    def _normalise(vectors: FloatArray) -> FloatArray:
        """Return L2-normalised copy of *vectors* (shape n×d, float32)."""
        vectors = vectors.copy()
        faiss.normalize_L2(vectors)
        return vectors

    # ------------------------------------------------------------------
    # VectorStore protocol implementation
    # ------------------------------------------------------------------

    async def add(self, vectors: FloatArray, ids: IntArray) -> None:
        """Normalise and insert *vectors* with their *ids*.

        Args:
            vectors: float32 array of shape (n, dimension).
            ids:     int64-compatible array of shape (n,).
        """
        vecs = self._to_float32_2d(vectors)
        if vecs.shape[1] != self._dimension:
            raise ValueError(f"Expected dimension {self._dimension}, got {vecs.shape[1]}")
        id_arr = np.array(ids, dtype=np.int64)
        if id_arr.shape[0] != vecs.shape[0]:
            raise ValueError(
                f"vectors and ids length mismatch: " f"{vecs.shape[0]} vs {id_arr.shape[0]}"
            )

        vecs = self._normalise(vecs)

        async with self._lock:
            self._index.add_with_ids(vecs, id_arr)

    async def query(self, vector: FloatArray, top_k: int) -> list[tuple[int, float]]:
        """Return top-k nearest neighbours sorted by descending similarity.

        Returns [] when the index contains no vectors.

        Args:
            vector: float32 array of shape (dimension,) or (1, dimension).
            top_k:  maximum number of results (capped by index size).
        """
        if self._index.ntotal == 0:
            return []

        vec = self._to_float32_2d(vector)
        if vec.shape[1] != self._dimension:
            raise ValueError(f"Expected dimension {self._dimension}, got {vec.shape[1]}")

        k = min(top_k, self._index.ntotal)
        vec = self._normalise(vec)

        # FAISS search is read-only; no lock needed (single event loop ensures
        # no concurrent mutation while awaiting).
        distances, indices = self._index.search(vec, k)

        results: list[tuple[int, float]] = []
        for idx, dist in zip(indices[0], distances[0], strict=False):
            if idx == -1:
                # FAISS uses -1 as a sentinel for "no result"
                continue
            results.append((int(idx), float(dist)))

        # Already sorted descending by FAISS; guard against any edge case.
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    async def remove_ids(self, ids: list[int]) -> None:
        """Remove vectors with the given IDs from the index.

        Args:
            ids: list of integer IDs previously passed to add().
        """
        id_arr = faiss.IDSelectorArray(np.array(ids, dtype=np.int64))
        async with self._lock:
            self._index.remove_ids(id_arr)

    def persist(self, path: Path) -> None:
        """Write the current index to *path* (synchronous).

        Args:
            path: destination file path; parent directory must exist.
        """
        faiss.write_index(self._index, str(path))

    def load(self, path: Path) -> None:
        """Replace the in-memory index by loading from *path* (synchronous).

        Args:
            path: path to a file previously written by persist().
        """
        loaded = faiss.read_index(str(path))
        # Wrap in IndexIDMap if the persisted index is the inner flat index.
        # Normally persist() always writes the outer IndexIDMap, so this
        # branch is a defensive fallback only.
        if not isinstance(loaded, faiss.IndexIDMap):
            loaded = faiss.IndexIDMap(loaded)
        self._index = loaded

    # ------------------------------------------------------------------
    # Convenience / diagnostics
    # ------------------------------------------------------------------

    @property
    def ntotal(self) -> int:
        """Number of vectors currently stored in the index."""
        return int(self._index.ntotal)

    @property
    def dimension(self) -> int:
        """Embedding dimensionality this store was created for."""
        return self._dimension
