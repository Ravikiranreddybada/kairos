"""Hybrid retrieval: BM25 (lexical) + dense vectors, fused with RRF.

Why hybrid (ADR-0011): supply-chain questions mix exact identifiers
("SUP03", "MOQ") that dense embeddings blur, with paraphrases ("late delivery
fine" vs "penalty") that BM25 misses. Reciprocal Rank Fusion combines the two
rankings without having to calibrate their score scales.

Chunking is structure-aware: split on markdown headings so each chunk is one
coherent section with its heading path as context, then window long sections
with overlap. Each chunk keeps ``source`` + ``section`` for citations.

Security: chunks are screened for prompt injection at index time. Flagged
chunks are kept (they may hold real facts) but marked ``untrusted`` and the
injected sentences are removed before text ever reaches the model.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from kairos.llm.embeddings import Embedder, HashingEmbedder, tokenize
from kairos.llm.guardrails import _INJ, looks_like_injection, redact_pii

CORPUS_DIR = Path(__file__).parent / "corpus"


@dataclass
class Chunk:
    id: str
    source: str
    section: str
    text: str
    untrusted: bool = False


@dataclass
class Hit:
    chunk: Chunk
    score: float
    ranks: dict[str, int] = field(default_factory=dict)


def chunk_markdown(source: str, text: str, max_words: int = 120, overlap: int = 30) -> list[Chunk]:
    title = ""
    sections: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif line.strip():
            if not sections:
                sections.append(("Overview", []))
            sections[-1][1].append(line.strip())
    chunks: list[Chunk] = []
    for heading, lines in sections:
        words = " ".join(lines).split()
        step = max(1, max_words - overlap)
        for i, start in enumerate(range(0, max(len(words), 1), step)):
            body = " ".join(words[start : start + max_words])
            if not body:
                continue
            chunks.append(Chunk(f"{source}:{heading}:{i}", source, heading, f"{title} > {heading}: {body}"))
            if start + max_words >= len(words):
                break
    return chunks


def _sanitize(chunk: Chunk) -> Chunk:
    if not looks_like_injection(chunk.text):
        return Chunk(chunk.id, chunk.source, chunk.section, redact_pii(chunk.text), chunk.untrusted)
    kept = [s for s in re.split(r"(?<=[.!?])\s+", chunk.text) if not _INJ.search(s)]
    return Chunk(chunk.id, chunk.source, chunk.section, redact_pii(" ".join(kept)), untrusted=True)


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = docs
        self.k1, self.b = k1, b
        self.avgdl = sum(map(len, docs)) / max(len(docs), 1)
        df: Counter[str] = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def scores(self, query: list[str]) -> np.ndarray:
        out = np.zeros(len(self.docs))
        for i, (tf, d) in enumerate(zip(self.tf, self.docs, strict=True)):
            norm = self.k1 * (1 - self.b + self.b * len(d) / self.avgdl)
            out[i] = sum(self.idf.get(t, 0.0) * tf[t] * (self.k1 + 1) / (tf[t] + norm) for t in query if t in tf)
        return out


class HybridIndex:
    def __init__(self, chunks: list[Chunk], embedder: Embedder | None = None, rrf_k: int = 60) -> None:
        self.chunks = [_sanitize(c) for c in chunks]
        self.embedder = embedder or HashingEmbedder()
        self.rrf_k = rrf_k
        self.bm25 = BM25([tokenize(c.text) for c in self.chunks])
        self.vectors = self.embedder.embed([c.text for c in self.chunks])

    @classmethod
    def from_dir(cls, path: Path = CORPUS_DIR, embedder: Embedder | None = None) -> HybridIndex:
        chunks: list[Chunk] = []
        for f in sorted(path.glob("*.md")):
            chunks.extend(chunk_markdown(f.stem, f.read_text()))
        return cls(chunks, embedder)

    def search(self, query: str, k: int = 4, candidates: int = 20, include_untrusted: bool = True) -> list[Hit]:
        lex = self.bm25.scores(tokenize(query))
        dense = self.vectors @ self.embedder.embed([query])[0]
        lex_rank = {int(i): r for r, i in enumerate(np.argsort(-lex)[:candidates]) if lex[i] > 0}
        dense_rank = {int(i): r for r, i in enumerate(np.argsort(-dense)[:candidates])}
        fused: dict[int, float] = {}
        for ranking in (lex_rank, dense_rank):
            for i, r in ranking.items():
                fused[i] = fused.get(i, 0.0) + 1.0 / (self.rrf_k + r + 1)
        order = sorted(fused, key=lambda i: -fused[i])
        hits = []
        for i in order:
            c = self.chunks[i]
            if c.untrusted and not include_untrusted:
                continue
            hits.append(Hit(c, round(fused[i], 5), {"bm25": lex_rank.get(i, -1), "dense": dense_rank.get(i, -1)}))
            if len(hits) == k:
                break
        return hits
