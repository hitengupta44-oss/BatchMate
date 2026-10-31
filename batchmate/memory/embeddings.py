"""Embeddings: bge-small-en on CPU, with a dependency-free hashing fallback.

Both produce 384-dim vectors so the pgvector column never changes.
"""
from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from .. import config

_TOKEN = re.compile(r"[a-z0-9+#]+")
_STOP = set("a an the of to in on and or is are was were for with at by it this that be as i you my".split())


class HashEmbedder:
    """Deterministic bag-of-words + bigram hashing. Good enough for tests and offline demos."""

    dim = config.EMBED_DIM

    def _vec(self, text: str) -> list[float]:
        toks = [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        v = [0.0] * self.dim
        for f in feats:
            h = int(hashlib.md5(f.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class STEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device="cpu")
        get_dim = getattr(self.model, "get_embedding_dimension", None) or self.model.get_sentence_embedding_dimension
        self.dim = get_dim()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()


@lru_cache(maxsize=1)
def get_embedder():
    if config.EMBED_MODEL.lower() != "hash":
        try:
            return STEmbedder(config.EMBED_MODEL)
        except Exception as e:  # missing package or no network for weights
            print(f"[embeddings] falling back to HashEmbedder ({e.__class__.__name__}: {e})")
    return HashEmbedder()


def embed_one(text: str) -> list[float]:
    return get_embedder().embed([text])[0]


# Optional accelerator for big batches (set by app.py on ZeroGPU Spaces).
_bulk = None
BULK_MIN = 16


def register_bulk_embedder(fn) -> None:
    global _bulk
    _bulk = fn


def embed_many(texts: list[str]) -> list[list[float]]:
    if _bulk is not None and len(texts) >= BULK_MIN:
        try:
            return _bulk(texts)
        except Exception as e:  # GPU quota exhausted or unavailable → CPU
            print(f"[embeddings] GPU batch failed, using CPU ({e.__class__.__name__})")
    return get_embedder().embed(texts)
