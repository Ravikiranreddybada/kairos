# ADR-0011: Hybrid BM25 + dense retrieval with RRF

Status: Accepted · Date: 2026-10-18

## Context

Policy questions contain exact identifiers (SUP03, MOQ, Severity 1) and paraphrases (fine vs. penalty). Dense-only retrieval blurs identifiers; BM25-only misses paraphrase.

## Decision

BM25 and dense rankings over structure-aware chunks, fused with Reciprocal Rank Fusion (k=60). Default embedder is deterministic feature hashing; production uses a hosted embedding model through the `Embedder` protocol. Chunks are sanitised for injection and PII at index time.

## Consequences

+ 100% expected-section hit rate in top-3 on the golden set.
+ No score calibration between retrievers (RRF uses ranks).
− Hashing embeddings are weak on true synonyms; acceptable at 21 chunks, replace before the corpus grows.
− No re-ranker yet; a cross-encoder is the next lever when the corpus is large.

## Alternatives considered

Dense-only with a vector DB (ops cost, identifier blur); BM25-only (paraphrase misses).
