"""Semantic answer cache with data-version invalidation.

Planners ask the same questions every Monday ("what should I reorder for
S01?"). Caching by meaning (cosine similarity of question embeddings) avoids
repeat LLM spend. The non-obvious part is **invalidation**: an answer about a
forecast is only valid for the forecast run that produced it. Every entry is
keyed by ``data_version`` (the champion ``run_id``); a new training run makes
every old entry unreachable without a flush.

Two more guards stop a "similar" question returning a *wrong* answer:

* **Entity guard** – identifiers and numbers (``S01``, ``SKU002``, ``99%``,
  dates) must match exactly. Embeddings put "reorder SKU002" and "reorder
  SKU003" close together; for a planner they are different questions.
* **Scope** – entries are partitioned by the caller's scope (the session's
  planner preferences), so an answer computed at a 99% service level is never
  served to a planner whose target is 95%.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from kairos.llm.embeddings import Embedder
from kairos.observability import CACHE_HITS

_ENTITY = re.compile(r"\b(?:S\d{2}|SKU\d{3}|SUP\d{2}|20\d{2}-\d{2}-\d{2}|\d+(?:\.\d+)?)\b", re.I)


def entities(question: str) -> frozenset[str]:
    """Ids, dates and numbers in a question: the parts that must match exactly for a cache hit."""
    return frozenset(m.upper() for m in _ENTITY.findall(question))


@dataclass
class _Entry:
    vec: np.ndarray
    question: str
    payload: dict[str, Any]
    data_version: str
    created: float
    entities: frozenset[str]
    scope: str


class SemanticCache:
    def __init__(self, embedder: Embedder, threshold: float = 0.92, ttl_s: float = 3600, max_items: int = 2000):
        self.embedder = embedder
        self.threshold = threshold
        self.ttl_s = ttl_s
        self.max_items = max_items
        self._items: list[_Entry] = []
        self._lock = threading.Lock()

    def get(self, question: str, data_version: str, scope: str = "") -> dict[str, Any] | None:
        v = self.embedder.embed([question])[0]
        ents = entities(question)
        now = time.time()
        with self._lock:
            live = [e for e in self._items if e.data_version == data_version and e.scope == scope
                    and e.entities == ents and now - e.created < self.ttl_s]
            if not live:
                CACHE_HITS.labels("miss").inc()
                return None
            sims = np.array([float(e.vec @ v) for e in live])
            best = int(np.argmax(sims))
            if sims[best] >= self.threshold:
                CACHE_HITS.labels("hit").inc()
                return {**live[best].payload, "cache": {"similarity": round(float(sims[best]), 4),
                                                        "matched_question": live[best].question}}
        CACHE_HITS.labels("miss").inc()
        return None

    def put(self, question: str, data_version: str, payload: dict[str, Any], scope: str = "") -> None:
        v = self.embedder.embed([question])[0]
        with self._lock:
            self._items.append(_Entry(v, question, payload, data_version, time.time(), entities(question), scope))
            if len(self._items) > self.max_items:
                self._items = self._items[-self.max_items :]
