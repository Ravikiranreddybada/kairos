# Observability

Code: `src/kairos/observability.py` (one module; ADR-0009).

## Three signals

**Logs** – JSON lines to stdout, one schema everywhere:
```json
{"ts":1792298262.17,"level":"INFO","logger":"kairos.span","msg":"tool.call",
 "trace_id":"4e76…","span_id":"9b1c…","parent_span_id":"503e…",
 "span":"tool.call","duration_ms":291.2,"status":"ok","tool":"get_forecast","is_error":false}
```

**Traces** – `trace()` sets a trace id per request (honours inbound
`x-trace-id`); `span()` records name, parent, duration, status and
attributes. Spans: `agent.ask`, `llm.call` (tier, model, tokens, cache
reads, cost), `tool.call`, `backtest.fold`, `pipeline.*`. Context is copied
into the tool thread pool so parallel tool calls keep their trace.
Swapping to OpenTelemetry (or Langfuse/LangSmith for LLM traces) changes
only this module.

**Metrics** – Prometheus at `/metrics`:

| Metric | Type | Labels | Alert idea |
|---|---|---|---|
| `kairos_http_request_seconds` | histogram | route, method, status | p95 forecast > 150 ms (10 m) |
| `kairos_llm_tokens_total` | counter | model, direction | sudden 3× vs 7-day baseline |
| `kairos_llm_cost_usd_total` | counter | model | daily spend > budget |
| `kairos_llm_call_seconds` | histogram | model | p95 > 15 s |
| `kairos_agent_tool_calls_total` | counter | tool, status | error ratio > 5% |
| `kairos_semantic_cache_total` | counter | result | hit rate drop after deploy |

## ML-specific monitoring

| What | How | Action |
|---|---|---|
| Data quality | Contract report stored per run (`quality.json`) | Block training on `error` |
| Forecast accuracy (online) | Weekly job: realised WAPE / bias by segment vs backtest | Alert if > 1.3× backtest WAPE for 2 weeks |
| Interval calibration (online) | Realised coverage of last 4 weeks | Alert outside 0.70–0.90 |
| Feature drift | PSI on top-10 features (train vs last 28 days) | Investigate > 0.2 |
| Champion age | `now − champion.promoted_at` | Alert > 8 days |
| Agent quality | Nightly real-model eval report (CI artifact) | Gate failure opens an issue |
| Planner overrides | Log accepted vs changed recommendations | Feeds roadmap item "online learning" |

## Dashboards (Grafana, provisioned by compose)

1. **API**: RPS, p50/p95/p99 by route, 4xx/5xx.
2. **Copilot**: questions/min, status mix (ok/cached/degraded/blocked), cost/hour, tokens by model, tool error ratio, cache hit rate.
3. **Models**: champion run id + age, backtest vs realised WAPE, coverage.
