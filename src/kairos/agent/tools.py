"""Agent tools: typed, validated, observable, safe to fail.

Each tool = pydantic input model + pure function over ``ToolContext``. The
same registry feeds (a) Claude tool definitions, (b) the MCP server and
(c) the REST API, so there is one implementation of every capability.

Design rules (see docs/03-system-design/agent-design.md):
* tools return compact JSON (the model pays for every token it reads)
* inputs are validated here even though the model "should" send valid JSON
* failures become ``{"error": ...}`` + ``is_error`` – the model can recover
  (retry with a fixed argument, or tell the user), the request never 500s
* tools are read-only; anything that changes the world needs a human
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field, ValidationError

from kairos.agent.sql_guard import UnsafeSQL, guard
from kairos.anomaly.detector import DetectorConfig, detect
from kairos.data.warehouse import SCHEMA_DOC, QueryTimeout, Warehouse
from kairos.decisions.ledger import DecisionLedger
from kairos.forecasting.service import ForecastService, NotFound, NotReady
from kairos.observability import TOOL_CALLS, span
from kairos.rag.index import HybridIndex
from kairos.rag.tree import DocTree

StoreId = Field(..., pattern=r"^S\d{2}$", description="Store id, e.g. S01")
SkuId = Field(..., pattern=r"^SKU\d{3}$", description="SKU id, e.g. SKU002")


class ForecastIn(BaseModel):
    store_id: str = StoreId
    sku_id: str = SkuId
    horizon_days: int = Field(28, ge=1, le=28, description="Days ahead (1-28)")


class PolicyIn(BaseModel):
    store_id: str = StoreId
    sku_id: str = SkuId
    service_level: float | None = Field(None, ge=0.5, lt=1.0, description="Target cycle service level, e.g. 0.95")
    lead_time_override_days: float | None = Field(None, gt=0, le=60, description="Scenario: assume this lead time")


class WhatIfIn(BaseModel):
    store_id: str = StoreId
    sku_id: str = SkuId
    start_date: str | None = Field(None, description="YYYY-MM-DD; defaults to tomorrow")
    days: int = Field(7, ge=1, le=14)


class AnomalyIn(BaseModel):
    store_id: str | None = Field(None, pattern=r"^S\d{2}$")
    sku_id: str | None = Field(None, pattern=r"^SKU\d{3}$")
    top_k: int = Field(5, ge=1, le=20)
    include_explained: bool = Field(False, description="Also return spikes explained by promo/festival/stockout")


class ExplainIn(BaseModel):
    store_id: str = StoreId
    sku_id: str = SkuId
    horizon_days: int = Field(28, ge=1, le=28, description="Days ahead to explain (1-28)")


class WorklistIn(BaseModel):
    store_id: str = StoreId
    service_level: float | None = Field(None, ge=0.5, lt=1.0, description="Target cycle service level")
    top_k: int = Field(10, ge=1, le=50)


class StressIn(BaseModel):
    store_id: str = StoreId
    sku_id: str = SkuId
    lead_time_delay_days: float = Field(0, ge=0, le=60, description="Scenario: supplier delivers this many days late")
    demand_shock_pct: float = Field(0, ge=-90, le=300, description="Scenario: demand runs this % above (+) or below (-) forecast")
    service_level: float | None = Field(None, ge=0.5, lt=1.0, description="Target cycle service level")


class PoolingIn(BaseModel):
    sku_id: str = SkuId
    service_level: float | None = Field(None, ge=0.5, lt=1.0, description="Target cycle service level")
    dc_to_store_days: float | None = Field(None, gt=0, le=14, description="DC -> store transfer days (default 2)")


class HealthIn(BaseModel):
    top_k: int = Field(5, ge=1, le=20)


class DecisionsIn(BaseModel):
    store_id: str | None = Field(None, pattern=r"^S\d{2}$")
    sku_id: str | None = Field(None, pattern=r"^SKU\d{3}$")
    status: str | None = Field(None, pattern=r"^(pending|approved|rejected)$")
    limit: int = Field(10, ge=1, le=50)


class BrowseIn(BaseModel):
    node_id: str | None = Field(None, max_length=200,
                                description="Omit for the outline; 'doc' for its sections; 'doc#Section' for full text")


class SqlIn(BaseModel):
    query: str = Field(..., max_length=4000, description="One read-only DuckDB SELECT over the documented schema")


class DocsIn(BaseModel):
    query: str = Field(..., max_length=500)
    k: int = Field(3, ge=1, le=8)


@dataclass
class ToolContext:
    wh: Warehouse
    forecasts: ForecastService
    index: HybridIndex
    default_service_level: float = 0.95
    sql_timeout_s: float = 5.0
    ledger: DecisionLedger | None = None  # read here; written only by humans through the API
    tree: DocTree | None = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    model: type[BaseModel]
    fn: Callable[[ToolContext, Any], dict[str, Any]]

    def definition(self) -> dict[str, Any]:
        schema = self.model.model_json_schema()
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        schema["additionalProperties"] = False
        return {"name": self.name, "description": self.description, "input_schema": schema}


def _forecast(ctx: ToolContext, a: ForecastIn) -> dict[str, Any]:
    r = ctx.forecasts.forecast(a.store_id, a.sku_id, a.horizon_days)
    # Compact weekly summary instead of 28 daily rows: fewer tokens, same decision value.
    daily = pd.DataFrame(r.pop("daily"))
    daily["week"] = pd.RangeIndex(len(daily)) // 7 + 1
    r["weekly"] = [
        {"week": int(w), "units": round(float(g.yhat.sum()), 1), "lo": round(float(g.lo.sum()), 1),
         "hi": round(float(g.hi.sum()), 1)}
        for w, g in daily.groupby("week")
    ]
    return r


def _policy(ctx: ToolContext, a: PolicyIn) -> dict[str, Any]:
    sl = a.service_level or ctx.default_service_level
    return ctx.forecasts.inventory_policy(a.store_id, a.sku_id, sl, a.lead_time_override_days)


def _what_if(ctx: ToolContext, a: WhatIfIn) -> dict[str, Any]:
    return ctx.forecasts.what_if_promo(a.store_id, a.sku_id, a.start_date, a.days)


def _anomalies(ctx: ToolContext, a: AnomalyIn) -> dict[str, Any]:
    sales = ctx.wh.sales(a.store_id, a.sku_id)
    flags = detect(sales[sales["date"] >= sales["date"].max() - pd.Timedelta(days=180)], DetectorConfig(threshold=5.0))
    if not a.include_explained:
        flags = flags[flags["explained_by"] == ""]
    flags = flags.head(a.top_k).assign(date=lambda d: d["date"].dt.date.astype(str))
    return {"window_days": 180, "count": len(flags),
            "anomalies": flags[["date", "store_id", "sku_id", "units_sold", "score", "explanation"]]
            .round(2).to_dict(orient="records")}


def _explain(ctx: ToolContext, a: ExplainIn) -> dict[str, Any]:
    return ctx.forecasts.explain(a.store_id, a.sku_id, a.horizon_days)


def _worklist(ctx: ToolContext, a: WorklistIn) -> dict[str, Any]:
    return ctx.forecasts.reorder_worklist(a.store_id, a.service_level or ctx.default_service_level, a.top_k)


def _stress(ctx: ToolContext, a: StressIn) -> dict[str, Any]:
    return ctx.forecasts.stress_test(a.store_id, a.sku_id, a.service_level or ctx.default_service_level,
                                     a.lead_time_delay_days, a.demand_shock_pct)


def _pooling(ctx: ToolContext, a: PoolingIn) -> dict[str, Any]:
    return ctx.forecasts.network_pooling(a.sku_id, a.service_level or ctx.default_service_level, a.dc_to_store_days)


def _health(ctx: ToolContext, a: HealthIn) -> dict[str, Any]:
    return ctx.forecasts.model_health(a.top_k)


def _decisions(ctx: ToolContext, a: DecisionsIn) -> dict[str, Any]:
    if ctx.ledger is None:
        raise LookupError("decision ledger is not configured")
    items = ctx.ledger.find(a.store_id, a.sku_id, a.status, a.limit)
    keep = ("id", "store_id", "sku_id", "status", "recommended_qty", "final_qty", "reason", "run_id",
            "hindsight_ideal_qty", "model_error", "planner_error")
    return {"count": len(items), "decisions": [{k: p[k] for k in keep} for p in items],
            "lessons": ctx.ledger.lessons(a.store_id, a.sku_id),
            "audit_chain": ctx.ledger.verify_chain()}


def _browse(ctx: ToolContext, a: BrowseIn) -> dict[str, Any]:
    if ctx.tree is None:
        raise LookupError("document tree is not configured")
    return ctx.tree.browse(a.node_id)


def _sql(ctx: ToolContext, a: SqlIn) -> dict[str, Any]:
    g = guard(a.query)
    df = ctx.wh.query(g.sql, timeout_s=ctx.sql_timeout_s)
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.date.astype(str)
    return {"sql": g.sql, "row_count": len(df), "columns": list(df.columns),
            "rows": json.loads(df.head(50).to_json(orient="records", double_precision=3, date_format="iso"))}


def _docs(ctx: ToolContext, a: DocsIn) -> dict[str, Any]:
    hits = ctx.index.search(a.query, k=a.k)
    return {"results": [
        {"source": h.chunk.source, "section": h.chunk.section, "text": h.chunk.text,
         "untrusted": h.chunk.untrusted, "score": h.score}
        for h in hits
    ]}


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool("get_forecast",
             "Probabilistic daily demand forecast for one store and SKU, summarised by week with an 80% "
             "prediction interval. Use for 'how much will we sell' questions.", ForecastIn, _forecast),
        Tool("inventory_policy",
             "Reorder decision for one store and SKU: safety stock, reorder point, order quantity, stockout "
             "probability and the cost of higher service levels. Use for 'should we order / how much' questions.",
             PolicyIn, _policy),
        Tool("what_if_promo",
             "Simulate running a promotion (15% discount) on a store/SKU: baseline vs promo units, uplift %, "
             "post-promo dip and net incremental units.", WhatIfIn, _what_if),
        Tool("explain_forecast",
             "Why a store/SKU forecast is what it is: baseline units per day and the % effect of each driver "
             "(recent demand level, seasonality, festival, promotion, price). Use for 'why' questions about a "
             "forecast.", ExplainIn, _explain),
        Tool("reorder_worklist",
             "Every SKU at one store ranked by stockout probability, with order quantities. Use for 'what should "
             "I reorder at <store>' questions that name no SKU.", WorklistIn, _worklist),
        Tool("detect_anomalies",
             "Unexplained demand anomalies in the last 180 days with robust scores and explanations.",
             AnomalyIn, _anomalies),
        Tool("run_sql",
             "Run ONE read-only DuckDB SELECT for aggregate questions about sales, stock, suppliers or "
             f"forecasts. Results capped at 200 rows. Schema:\n{SCHEMA_DOC}\n"
             "fact_forecast(date, store_id, sku_id, yhat, lo, hi, model, run_id)", SqlIn, _sql),
        Tool("simulate_supply_risk",
             "Monte-Carlo stress test of the reorder policy for one store/SKU over the next 28 days: stockout "
             "probability, fill rate, lost units and ending stock, as-is and under a scenario (supplier delay in "
             "days and/or demand shock %). Also gives a distribution-free reorder point and how much to order now. "
             "Use for 'what if the supplier is late', 'how risky', 'how many sales would we lose' questions.",
             StressIn, _stress),
        Tool("network_pooling",
             "Multi-echelon view for one SKU across all stores: total safety stock if each store buys direct vs a "
             "distribution centre holding one pooled buffer (uses measured demand correlation), units and holding "
             "cost saved. Use for DC, pooling, network or echelon questions.", PoolingIn, _pooling),
        Tool("model_health",
             "Is the forecast model still valid? Demand drift (PSI) and level shift of recent sales vs the "
             "published forecast for every series, champion age and backtest accuracy, with a retrain "
             "recommendation. Use for drift, stale model or 'can I trust the forecast' questions.",
             HealthIn, _health),
        Tool("decision_history",
             "Past purchase-order proposals and what humans decided (approved, rejected, overridden quantity and "
             "reason), plus lessons learned from overrides and realised outcomes (does overriding help?) and the "
             "audit-chain integrity. Read-only. Use for override, approval, track-record or 'what did we decide' "
             "questions.", DecisionsIn, _decisions),
        Tool("browse_docs",
             "Navigate policy documents like a table of contents: no node_id returns every document with its "
             "sections; a document id returns its section summaries; 'doc#Section' returns the full section text. "
             "Use for outlines, 'what does X cover' and reading a whole section. Cite as doc#Section.",
             BrowseIn, _browse),
        Tool("search_docs",
             "Search internal policy documents (inventory policy, supplier contracts, promotion playbook, "
             "escalation SOP). Use for rules, targets, penalties and procedures. Cite source#section.",
             DocsIn, _docs),
    ]
}


def tool_definitions() -> list[dict[str, Any]]:
    return [TOOLS[n].definition() for n in sorted(TOOLS)]  # sorted = stable prompt-cache prefix


@dataclass
class ToolOutcome:
    name: str
    input: dict[str, Any]
    output: dict[str, Any]
    is_error: bool
    latency_ms: float


def execute(ctx: ToolContext, name: str, raw_input: dict[str, Any]) -> ToolOutcome:
    start = time.perf_counter()
    tool = TOOLS.get(name)
    with span("tool.call", tool=name) as rec:
        try:
            if tool is None:
                raise LookupError(f"unknown tool {name}")
            args = tool.model.model_validate(raw_input)
            out, err = tool.fn(ctx, args), False
        except ValidationError as e:
            out, err = {"error": "invalid arguments",
                        "details": [f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]}, True
        except UnsafeSQL as e:
            out, err = {"error": f"query rejected by SQL guard: {e}"}, True
        except (NotFound, NotReady, LookupError, ValueError, QueryTimeout) as e:
            out, err = {"error": str(e).strip("'\"")}, True
        except Exception as e:  # tool bugs must not kill the conversation
            out, err = {"error": f"internal tool error: {type(e).__name__}"}, True
        rec["is_error"] = err
    TOOL_CALLS.labels(name, "error" if err else "ok").inc()
    return ToolOutcome(name, raw_input, out, err, (time.perf_counter() - start) * 1000)
