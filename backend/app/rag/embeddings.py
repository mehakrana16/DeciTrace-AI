"""Embedding backends for the retrieval pipeline.

Two interchangeable implementations behind one interface:

``SentenceTransformerEmbedder``
    The production path — dense semantic embeddings from
    ``sentence-transformers/all-MiniLM-L6-v2``.

``TfidfHashingEmbedder``
    A deterministic, offline, dependency-light fallback (sublinear TF-IDF over
    word unigrams/bigrams plus character 3-grams, then a signed hashing trick
    into a fixed-width L2-normalised vector). Retrieval quality is lower than a
    transformer but the pipeline is *real*: the same index, the same cosine
    search, the same row-level hits.

``auto`` (default) tries Sentence Transformers once and silently degrades to
the TF-IDF backend if the model cannot be loaded (no network, no torch, no
model cache). ``get_embedder()`` never raises.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Protocol, Sequence

import numpy as np

from ..config import settings

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9\-_]+")


class Embedder(Protocol):
    name: str
    dim: int

    def encode(self, texts: Sequence[str]) -> np.ndarray:  # (n, dim) float32, L2-normalised
        ...


# ---------------------------------------------------------------------------
# Fallback: deterministic TF-IDF + signed hashing
# ---------------------------------------------------------------------------
class TfidfHashingEmbedder:
    """Offline deterministic embedder. No network, no model download."""

    name = "tfidf-hashing"

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self._df: Counter[str] = Counter()
        self._n_docs = 0
        self._fitted = False

    # -- tokenisation ----------------------------------------------------
    @staticmethod
    def _tokens(text: str) -> list[str]:
        text = text.lower()
        words = _WORD_RE.findall(text)
        grams = [f"{a}_{b}" for a, b in zip(words, words[1:])]  # word bigrams
        chars = [
            f"c:{text[i:i + 3]}"
            for i in range(max(0, len(text) - 2))
            if " " not in text[i:i + 3]
        ][:400]
        return words + grams + chars

    def fit(self, texts: Sequence[str]) -> "TfidfHashingEmbedder":
        self._df = Counter()
        for text in texts:
            self._df.update(set(self._tokens(text)))
        self._n_docs = max(1, len(texts))
        self._fitted = True
        return self

    def _idf(self, token: str) -> float:
        if not self._fitted:
            return 1.0
        df = self._df.get(token, 0)
        return math.log((1 + self._n_docs) / (1 + df)) + 1.0

    def _bucket(self, token: str) -> tuple[int, float]:
        h = hash_token(token)
        return h % self.dim, 1.0 if (h >> 63) & 1 == 0 else -1.0

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            counts = Counter(self._tokens(text))
            if not counts:
                continue
            for token, tf in counts.items():
                weight = (1.0 + math.log(tf)) * self._idf(token)
                idx, sign = self._bucket(token)
                out[i, idx] += sign * weight
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms


def hash_token(token: str) -> int:
    """Stable 64-bit hash (independent of PYTHONHASHSEED)."""
    h = 1469598103934665603
    for byte in token.encode("utf-8"):
        h ^= byte
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


# ---------------------------------------------------------------------------
# Sentence Transformers backend
# ---------------------------------------------------------------------------
class SentenceTransformerEmbedder:
    name = "sentence-transformers"

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # imported lazily

        self._model = SentenceTransformer(model_name)
        self.model_name = model_name
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode(
            list(texts), convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
_CACHE: dict[str, Embedder] = {}


def get_embedder() -> Embedder:
    """Return the active embedder, degrading gracefully. Never raises."""
    requested = settings.EMBEDDING_BACKEND
    if requested in _CACHE:
        return _CACHE[requested]

    embedder: Embedder | None = None
    if requested in {"auto", "sentence-transformers"}:
        try:
            embedder = SentenceTransformerEmbedder(settings.EMBEDDING_MODEL)
        except Exception as exc:  # pragma: no cover - environment dependent
            if requested == "sentence-transformers":
                print(f"[rag] sentence-transformers unavailable ({exc}); using tfidf fallback")
            embedder = None

    if embedder is None:
        embedder = TfidfHashingEmbedder()

    _CACHE[requested] = embedder
    return embedder
