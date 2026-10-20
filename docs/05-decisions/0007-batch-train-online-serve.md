# ADR-0007: Batch training, read-only serving (CQRS)

Status: Accepted · Date: 2026-10-18

## Context

Forecasts are needed by dashboards, the API, the copilot and MCP clients. If each request ran a model, latency, cost and consistency would all suffer, and a model bug would be a request-path outage.

## Decision

Training is a job (`kairos train`, K8s CronJob) that writes `fact_forecast` and `fact_forecast_hierarchy` atomically. Serving (`ForecastService`) only reads, plus one small in-memory GBM for what-if. The service hot-reloads when the champion pointer changes.

## Consequences

+ O(1) reads; p95 lookups in milliseconds; the API has no model in its critical path.
+ Every channel shows the same number on the same day.
+ Training scales independently (bigger node, Ray) without touching the API.
− Forecasts are as fresh as the last run (weekly; daily is a schedule change).

## Alternatives considered

Online inference per request (rejected: latency, consistency); streaming updates (not needed at weekly planning cadence).
