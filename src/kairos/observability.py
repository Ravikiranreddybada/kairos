"""Structured logging, lightweight tracing and Prometheus metrics.

Design: one module, zero hard dependency on a tracing backend. Spans are
emitted as JSON log lines carrying ``trace_id``/``span_id`` so any log
pipeline (Loki, CloudWatch, Datadog) can rebuild the tree. Swapping in
OpenTelemetry later only touches this file (see ADR-0009).
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from prometheus_client import Counter, Histogram

_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
_span_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("span_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": round(record.created, 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": _trace_id.get(),
            "span_id": _span_id.get(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)  # stdout stays clean for CLI JSON output
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level)


def get_logger(name: str) -> logging.LoggerAdapter[logging.Logger]:
    class _Adapter(logging.LoggerAdapter[logging.Logger]):
        def process(self, msg: Any, kwargs: Any) -> tuple[Any, Any]:
            fields = kwargs.pop("fields", None)
            if fields:
                kwargs.setdefault("extra", {})["fields"] = fields
            return msg, kwargs

    return _Adapter(logging.getLogger(name), {})


def new_trace_id() -> str:
    return uuid.uuid4().hex


def current_trace_id() -> str | None:
    return _trace_id.get()


@contextmanager
def trace(trace_id: str | None = None) -> Iterator[str]:
    tid = trace_id or new_trace_id()
    token = _trace_id.set(tid)
    try:
        yield tid
    finally:
        try:
            _trace_id.reset(token)
        except ValueError:  # generator resumed in another thread/context (e.g. SSE)
            _trace_id.set(None)


_log = get_logger("kairos.span")


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
    """Time a unit of work. Mutate the yielded dict to attach result attributes."""
    sid = uuid.uuid4().hex[:16]
    parent = _span_id.get()
    token = _span_id.set(sid)
    record: dict[str, Any] = dict(attrs)
    start = time.perf_counter()
    status = "ok"
    try:
        yield record
    except Exception:
        status = "error"
        raise
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        _span_id.reset(token)
        _log.info(
            name,
            fields={"span": name, "span_id": sid, "parent_span_id": parent, "duration_ms": round(elapsed_ms, 2),
                    "status": status, **record},
        )


# --- Metrics ----------------------------------------------------------------
HTTP_LATENCY = Histogram(
    "kairos_http_request_seconds", "HTTP latency", ["route", "method", "status"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
LLM_TOKENS = Counter("kairos_llm_tokens_total", "LLM tokens", ["model", "direction"])
LLM_COST = Counter("kairos_llm_cost_usd_total", "LLM spend in USD", ["model"])
LLM_LATENCY = Histogram("kairos_llm_call_seconds", "LLM call latency", ["model"])
TOOL_CALLS = Counter("kairos_agent_tool_calls_total", "Agent tool calls", ["tool", "status"])
CACHE_HITS = Counter("kairos_semantic_cache_total", "Semantic cache lookups", ["result"])
