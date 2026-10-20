"""Embeddings behind an interface.

Default: ``HashingEmbedder`` – feature-hashed word uni/bi-grams + char
trigrams, L2-normalised. It is deterministic, dependency-free and good enough
for a small policy corpus; it also makes tests reproducible. In production
swap in a hosted embedding model via the same ``Embedder`` protocol (ADR-0011).
"""

from __future__ import annotations

import hashlib
import itertools
import re
from typing import Protocol

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    ["a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "are", "be", "by", "with", "what", "which", "how", "do", "does", "should", "we", "our", "at", "as", "from", "it", "this", "that", "i", "me", "my", "you", "your", "can", "will"]
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def _idx(self, feat: str) -> tuple[int, float]:
        h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "little")
        return h % self.dim, (1.0 if (h >> 63) & 1 else -1.0)

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            toks = tokenize(text)
            feats = toks + [f"{a}_{b}" for a, b in itertools.pairwise(toks)]
            for t in toks:
                padded = f"#{t}#"
                feats.extend(padded[i : i + 3] for i in range(len(padded) - 2))
            for f in feats:
                i, sign = self._idx(f)
                out[row, i] += sign
            n = np.linalg.norm(out[row])
            if n > 0:
                out[row] /= n
        return out
