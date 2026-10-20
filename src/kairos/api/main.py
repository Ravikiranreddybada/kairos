"""Kairos REST API.

Thin delivery layer: validation, auth, rate limits, tracing, error mapping.
All behaviour lives in the domain packages, reached through ``bootstrap``.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.concurrency import run_in_threadpool

from kairos import __version__
from kairos.anomaly.detector import DetectorConfig, detect
from kairos.api.schemas import (
    ChatRequest,
    ChatResponse,
    DecideRequest,
    OutcomeRequest,
    PolicyRequest,
    ProposalRequest,
    StressRequest,
    TrainResponse,
    WhatIfRequest,
)
from kairos.api.security import (
    TokenBucket,
    require_admin_key,
    require_api_key,
    require_approver_key,
)
from kairos.bootstrap import System, build
from kairos.config import get_settings
from kairos.decisions.ledger import LedgerError
from kairos.forecasting.service import NotFound, NotReady
from kairos.observability import HTTP_LATENCY, configure_logging, get_logger, new_trace_id, trace

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    if not hasattr(app.state, "system"):  # tests inject their own System
        app.state.system = build(settings)
    app.state.limiter = TokenBucket(app.state.system.settings.rate_limit_per_min)
    app.state.training = asyncio.Lock()
    yield


app = FastAPI(title="Kairos", version=__version__, lifespan=lifespan,
              description="Supply-chain decision intelligence: forecasts, inventory policy and a grounded copilot.")


@app.middleware("http")
async def observe(request: Request, call_next: Any) -> Any:
    tid = request.headers.get("x-trace-id") or new_trace_id()
    start = time.perf_counter()
    with trace(tid):
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error", fields={"path": request.url.path})
            response = JSONResponse({"detail": "internal error", "trace_id": tid}, status_code=500)
    route = request.scope.get("route")
    HTTP_LATENCY.labels(getattr(route, "path", "unmatched"), request.method, str(response.status_code)).observe(
        time.perf_counter() - start)
    response.headers["x-trace-id"] = tid
    return response


@app.exception_handler(NotReady)
async def _not_ready(_: Request, exc: NotReady) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=503)


@app.exception_handler(NotFound)
async def _not_found(_: Request, exc: NotFound) -> JSONResponse:
    return JSONResponse({"detail": str(exc).strip("'\"")}, status_code=404)


@app.exception_handler(LedgerError)
async def _ledger_conflict(_: Request, exc: LedgerError) -> JSONResponse:
    return JSONResponse({"detail": str(exc).strip("'\"")}, status_code=409)


def system(request: Request) -> System:
    sys_: System = request.app.state.system
    return sys_


# ---------------------------------------------------------------- health / ops
@app.get("/healthz", tags=["ops"])
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/readyz", tags=["ops"])
def readyz(s: System = Depends(system)) -> JSONResponse:
    champion = s.forecasts.registry.champion()
    ok = champion is not None
    return JSONResponse({"ready": ok, "champion": champion}, status_code=200 if ok else 503)


@app.get("/metrics", tags=["ops"])
def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ------------------------------------------------------------------ decisions
@app.get("/v1/model", tags=["forecast"])
def model_card(s: System = Depends(system), _: str = Depends(require_api_key)) -> dict[str, Any]:
    return s.forecasts.model_card()


@app.get("/v1/forecast/{store_id}/{sku_id}", tags=["forecast"])
def forecast(store_id: str, sku_id: str, horizon_days: int = Query(28, ge=1, le=28),
             s: System = Depends(system), _: str = Depends(require_api_key)) -> dict[str, Any]:
    return s.forecasts.forecast(store_id.upper(), sku_id.upper(), horizon_days)


@app.get("/v1/forecast/{store_id}/{sku_id}/explain", tags=["forecast"])
def explain(store_id: str, sku_id: str, horizon_days: int = Query(28, ge=1, le=28),
            s: System = Depends(system), _: str = Depends(require_api_key)) -> dict[str, Any]:
    return s.forecasts.explain(store_id.upper(), sku_id.upper(), horizon_days)


@app.get("/v1/inventory/worklist/{store_id}", tags=["inventory"])
def worklist(store_id: str, service_level: float = Query(0.95, ge=0.5, lt=1.0), top_k: int = Query(10, ge=1, le=50),
             s: System = Depends(system), _: str = Depends(require_api_key)) -> dict[str, Any]:
    return s.forecasts.reorder_worklist(store_id.upper(), service_level, top_k)


@app.post("/v1/inventory/policy", tags=["inventory"])
def inventory_policy(req: PolicyRequest, s: System = Depends(system), _: str = Depends(require_api_key)
                     ) -> dict[str, Any]:
    return s.forecasts.inventory_policy(req.store_id, req.sku_id, req.service_level, req.lead_time_override_days)


@app.post("/v1/whatif/promo", tags=["forecast"])
def what_if(req: WhatIfRequest, s: System = Depends(system), _: str = Depends(require_api_key)) -> dict[str, Any]:
    return s.forecasts.what_if_promo(req.store_id, req.sku_id, req.start_date, req.days)


@app.post("/v1/inventory/stress-test", tags=["inventory"])
def stress_test(req: StressRequest, s: System = Depends(system), _: str = Depends(require_api_key)
                ) -> dict[str, Any]:
    return s.forecasts.stress_test(req.store_id, req.sku_id, req.service_level, req.lead_time_delay_days,
                                   req.demand_shock_pct)


@app.get("/v1/inventory/network/{sku_id}", tags=["inventory"])
def network(sku_id: str, service_level: float = Query(0.95, ge=0.5, lt=1.0),
            dc_to_store_days: float | None = Query(None, gt=0, le=14),
            s: System = Depends(system), _: str = Depends(require_api_key)) -> dict[str, Any]:
    return s.forecasts.network_pooling(sku_id.upper(), service_level, dc_to_store_days)


@app.get("/v1/model/health", tags=["forecast"])
def model_health(top_k: int = Query(5, ge=1, le=50), s: System = Depends(system),
                 _: str = Depends(require_api_key)) -> dict[str, Any]:
    return s.forecasts.model_health(top_k)


# ------------------------------------------------------------- decisions (HITL)
# The copilot only reads the ledger. Humans write it: a planner proposes, a *different*
# approver signs off (four-eyes), outcomes feed lessons. Every event is hash-chained.
@app.post("/v1/decisions/proposals", status_code=201, tags=["decisions"])
def propose(req: ProposalRequest, s: System = Depends(system), kid: str = Depends(require_api_key)
            ) -> dict[str, Any]:
    snapshot = s.forecasts.inventory_policy(req.store_id, req.sku_id, req.service_level)
    if not snapshot["decision"]["should_order"]:
        raise HTTPException(409, f"no order recommended: {snapshot['decision']['rationale']}")
    return s.ledger.propose(snapshot, actor=kid)


@app.get("/v1/decisions/proposals", tags=["decisions"])
def proposals(store_id: str | None = None, sku_id: str | None = None,
              status: str | None = Query(None, pattern="^(pending|approved|rejected)$"),
              limit: int = Query(20, ge=1, le=200), s: System = Depends(system),
              _: str = Depends(require_api_key)) -> dict[str, Any]:
    items = s.ledger.find(store_id, sku_id, status, limit)
    return {"count": len(items), "items": items}


@app.get("/v1/decisions/proposals/{proposal_id}", tags=["decisions"])
def proposal(proposal_id: str, s: System = Depends(system), _: str = Depends(require_api_key)) -> dict[str, Any]:
    try:
        return {**s.ledger.get(proposal_id), "audit": s.ledger.audit_log(proposal_id)}
    except LedgerError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/v1/decisions/proposals/{proposal_id}/approve", tags=["decisions"])
def approve(proposal_id: str, req: DecideRequest, s: System = Depends(system),
            kid: str = Depends(require_approver_key)) -> dict[str, Any]:
    return s.ledger.decide(proposal_id, True, actor=kid, qty=req.qty, reason=req.reason)


@app.post("/v1/decisions/proposals/{proposal_id}/reject", tags=["decisions"])
def reject(proposal_id: str, req: DecideRequest, s: System = Depends(system),
           kid: str = Depends(require_approver_key)) -> dict[str, Any]:
    return s.ledger.decide(proposal_id, False, actor=kid, reason=req.reason)


@app.post("/v1/decisions/proposals/{proposal_id}/outcome", tags=["decisions"])
def outcome(proposal_id: str, req: OutcomeRequest, s: System = Depends(system),
            kid: str = Depends(require_api_key)) -> dict[str, Any]:
    return s.ledger.record_outcome(proposal_id, req.actual_demand, actor=kid)


@app.get("/v1/decisions/lessons", tags=["decisions"])
def lessons(store_id: str | None = None, sku_id: str | None = None, s: System = Depends(system),
            _: str = Depends(require_api_key)) -> dict[str, Any]:
    return {"lessons": s.ledger.lessons(store_id, sku_id)}


@app.get("/v1/decisions/audit/verify", tags=["decisions"])
def verify_audit(s: System = Depends(system), _: str = Depends(require_api_key)) -> dict[str, Any]:
    return s.ledger.verify_chain()


@app.get("/v1/anomalies", tags=["anomaly"])
def anomalies(store_id: str | None = None, sku_id: str | None = None, limit: int = Query(20, ge=1, le=200),
              threshold: float = Query(5.0, ge=2.0, le=20.0), s: System = Depends(system),
              _: str = Depends(require_api_key)) -> dict[str, Any]:
    flags = detect(s.wh.sales(store_id, sku_id), DetectorConfig(threshold=threshold)).head(limit)
    flags["date"] = flags["date"].dt.date.astype(str)
    return {"count": len(flags), "anomalies": json.loads(flags.round(3).to_json(orient="records"))}


# --------------------------------------------------------------------- agent
@app.post("/v1/agent/chat", response_model=ChatResponse, tags=["agent"])
async def chat(req: ChatRequest, s: System = Depends(system), _: str = Depends(require_api_key)) -> ChatResponse:
    # The graph is sync (LLM + DuckDB calls); run it off the event loop.
    res = await run_in_threadpool(s.copilot.ask, req.message, req.session_id)
    return ChatResponse(**{k: v for k, v in res.to_dict().items() if k in ChatResponse.model_fields})


@app.post("/v1/agent/chat/stream", tags=["agent"])
async def chat_stream(req: ChatRequest, s: System = Depends(system), _: str = Depends(require_api_key)
                      ) -> StreamingResponse:
    """Server-sent events: one event per graph step, then the final result."""
    def events() -> Any:
        for ev in s.copilot.stream(req.message, req.session_id):
            yield f"event: {ev['event']}\ndata: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------- admin
@app.post("/v1/admin/train", response_model=TrainResponse, status_code=202, tags=["admin"])
async def trigger_train(request: Request, background: BackgroundTasks, s: System = Depends(system),
                        _: str = Depends(require_admin_key)) -> TrainResponse:
    lock: asyncio.Lock = request.app.state.training
    if lock.locked():
        raise HTTPException(409, "training already running")
    await lock.acquire()  # take it now: checking then acquiring later let two requests both start a run

    async def job() -> None:
        from kairos.forecasting.pipeline import train

        try:
            await run_in_threadpool(train, s.wh, s.settings)
        finally:
            lock.release()

    background.add_task(job)
    return TrainResponse(accepted=True, detail="training started; poll /v1/model for the new champion")


@app.post("/v1/admin/rollback", tags=["admin"])
async def trigger_rollback(request: Request, s: System = Depends(system), _: str = Depends(require_admin_key)
                           ) -> dict[str, str]:
    """Restore the previous champion and re-serve its forecasts (not just flip the pointer)."""
    from kairos.forecasting.pipeline import rollback

    lock: asyncio.Lock = request.app.state.training
    if lock.locked():
        raise HTTPException(409, "training running; roll back after it finishes")
    async with lock:
        try:
            champion = await run_in_threadpool(rollback, s.wh, s.settings)
        except (RuntimeError, FileNotFoundError) as e:
            raise HTTPException(409, str(e)) from e
    return {"champion": champion}
