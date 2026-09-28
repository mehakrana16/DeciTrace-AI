"""Vector index (FAISS when available, exact numpy cosine otherwise)."""
from __future__ import annotations

from typing import Sequence

import numpy as np

from ..config import settings


class VectorIndex:
    """Cosine-similarity index over L2-normalised vectors.

    Uses ``faiss.IndexFlatIP`` when FAISS is importable (exact inner-product
    search over normalised vectors == cosine similarity) and falls back to a
    dense numpy matmul otherwise. Both paths return identical orderings.
    """

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.backend = "numpy"
        self._vectors: np.ndarray | None = None
        self._faiss_index = None

        if settings.VECTOR_BACKEND in {"auto", "faiss"}:
            try:
                import faiss  # type: ignore

                self._faiss_index = faiss.IndexFlatIP(dim)
                self.backend = "faiss"
            except Exception:  # pragma: no cover
                if settings.VECTOR_BACKEND == "faiss":
                    print("[rag] faiss requested but unavailable; using exact numpy search")
                self._faiss_index = None
                self.backend = "numpy"

    # ------------------------------------------------------------------
    def add(self, vectors: np.ndarray) -> None:
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[1] != self.dim:
            raise ValueError(f"expected (n, {self.dim}) vectors, got {vectors.shape}")
        self._vectors = vectors if self._vectors is None else np.vstack([self._vectors, vectors])
        if self._faiss_index is not None:
            self._faiss_index.add(vectors)

    @property
    def size(self) -> int:
        return 0 if self._vectors is None else int(self._vectors.shape[0])

    def search(self, query: np.ndarray, k: int) -> list[tuple[int, float]]:
        """Return ``[(row_index, cosine_score), ...]`` ordered by descending score."""
        if self.size == 0 or k <= 0:
            return []
        query = np.ascontiguousarray(query, dtype=np.float32)
        if query.ndim == 2:
            query = query[0]
        query = query.reshape(1, -1)
        k = min(k, self.size)

        if self._faiss_index is not None:
            scores, indices = self._faiss_index.search(query, k)
            return [
                (int(i), float(s))
                for i, s in zip(indices[0], scores[0])
                if i >= 0
            ]

        assert self._vectors is not None
        scores = self._vectors @ query[0]
        order = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in order]


class NumpyIndex(VectorIndex):
    """Backwards-compatible alias."""


def build_index(vectors: Sequence[np.ndarray] | np.ndarray, dim: int) -> VectorIndex:
    index = VectorIndex(dim)
    array = np.asarray(vectors, dtype=np.float32)
    if array.size:
        index.add(array)
    return index
