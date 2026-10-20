"""Composition root: the only place where concrete implementations are wired.

API, MCP server, CLI and tests all build the system through ``build()`` so
they cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass

from kairos.agent.graph import Copilot
from kairos.agent.memory import Memory
from kairos.agent.tools import ToolContext
from kairos.config import Settings, get_settings
from kairos.data.synthetic import generate
from kairos.data.warehouse import Warehouse
from kairos.decisions.ledger import DecisionLedger
from kairos.forecasting.service import ForecastService
from kairos.llm.cache import SemanticCache
from kairos.llm.client import LLMClient, build_client
from kairos.llm.embeddings import HashingEmbedder
from kairos.rag.index import HybridIndex
from kairos.rag.tree import DocTree


@dataclass
class System:
    settings: Settings
    wh: Warehouse
    forecasts: ForecastService
    index: HybridIndex
    ctx: ToolContext
    copilot: Copilot

    @property
    def ledger(self) -> DecisionLedger:
        assert self.ctx.ledger is not None
        return self.ctx.ledger


def seed(settings: Settings, wh: Warehouse | None = None) -> Warehouse:
    wh = wh or Warehouse(settings.warehouse_path)
    wh.load(generate(settings.n_stores, settings.n_skus, settings.history_days, seed=settings.seed))
    return wh


def build(settings: Settings | None = None, llm: LLMClient | None = None, wh: Warehouse | None = None,
          use_cache: bool = True) -> System:
    settings = settings or get_settings()
    wh = wh or Warehouse(settings.warehouse_path)
    forecasts = ForecastService(wh, settings)
    embedder = HashingEmbedder()
    index = HybridIndex.from_dir(embedder=embedder)
    ledger = DecisionLedger(settings.decisions_path if settings.env != "test" else ":memory:")
    ctx = ToolContext(wh=wh, forecasts=forecasts, index=index, sql_timeout_s=settings.sql_timeout_s,
                      ledger=ledger, tree=DocTree.from_dir())
    memory = Memory(settings.memory_path if settings.env != "test" else ":memory:")
    cache = SemanticCache(embedder, settings.semantic_cache_threshold) if use_cache else None
    copilot = Copilot(ctx, llm or build_client(settings), settings, memory=memory, cache=cache)
    return System(settings, wh, forecasts, index, ctx, copilot)
