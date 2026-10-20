"""Public API contracts. Versioned under /v1; breaking changes go to /v2."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field("default", pattern=r"^[A-Za-z0-9_\-]{1,64}$")


class ChatResponse(BaseModel):
    answer: str
    status: str
    tier: str
    tool_calls: list[dict[str, Any]]
    citations: list[str]
    grounding: dict[str, Any]
    usage: dict[str, int]
    cost_usd: float
    latency_ms: float
    trace_id: str | None
    data_version: str


class PolicyRequest(BaseModel):
    store_id: str = Field(..., pattern=r"^S\d{2}$")
    sku_id: str = Field(..., pattern=r"^SKU\d{3}$")
    service_level: float = Field(0.95, ge=0.5, lt=1.0)
    lead_time_override_days: float | None = Field(None, gt=0, le=60)


class WhatIfRequest(BaseModel):
    store_id: str = Field(..., pattern=r"^S\d{2}$")
    sku_id: str = Field(..., pattern=r"^SKU\d{3}$")
    start_date: str | None = None
    days: int = Field(7, ge=1, le=14)


class TrainResponse(BaseModel):
    accepted: bool
    detail: str


class StressRequest(BaseModel):
    store_id: str = Field(..., pattern=r"^S\d{2}$")
    sku_id: str = Field(..., pattern=r"^SKU\d{3}$")
    service_level: float = Field(0.95, ge=0.5, lt=1.0)
    lead_time_delay_days: float = Field(0, ge=0, le=60)
    demand_shock_pct: float = Field(0, ge=-90, le=300)


class ProposalRequest(BaseModel):
    store_id: str = Field(..., pattern=r"^S\d{2}$")
    sku_id: str = Field(..., pattern=r"^SKU\d{3}$")
    service_level: float = Field(0.95, ge=0.5, lt=1.0)


class DecideRequest(BaseModel):
    qty: float | None = Field(None, ge=0, le=1_000_000, description="Override quantity (needs a reason)")
    reason: str | None = Field(None, max_length=500)


class OutcomeRequest(BaseModel):
    actual_demand: float = Field(..., ge=0, le=10_000_000,
                                 description="Realised demand over the decision's lead time + review period")
