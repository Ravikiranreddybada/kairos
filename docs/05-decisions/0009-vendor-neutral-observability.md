# ADR-0009: Vendor-neutral observability in one module

Status: Accepted · Date: 2026-10-18

## Context

We need logs, traces and metrics for both ML and LLM behaviour, but the target environment (Datadog, Grafana, CloudWatch, Langfuse, LangSmith) is client-dependent.

## Decision

`observability.py` provides JSON logs with trace/span ids, a `span()` context manager and Prometheus metrics. Nothing else imports a telemetry vendor.

## Consequences

+ Works everywhere today (stdout + /metrics). One file changes to adopt OpenTelemetry or an LLM-tracing vendor.
− Our spans are not OTel spans yet, so no automatic distributed tracing across services until the swap.

## Alternatives considered

OpenTelemetry SDK from day one (heavier setup for a single service); LangSmith/Langfuse only (LLM-only view; vendor lock).
