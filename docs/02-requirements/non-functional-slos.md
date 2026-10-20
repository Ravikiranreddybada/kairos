# Non-functional requirements and SLOs

## Service level objectives (production targets)

| SLI | SLO | Window | Notes |
|---|---|---|---|
| Availability of `/v1/forecast`, `/v1/inventory/*` | 99.9% non-5xx | 30 days | Read path; no LLM dependency |
| Latency `/v1/forecast` | p95 < 150 ms, p99 < 400 ms | 7 days | Indexed DuckDB/Postgres lookup |
| Availability of `/v1/agent/chat` | 99.5% non-5xx | 30 days | Degraded answers count as available |
| Latency `/v1/agent/chat` | p50 < 4 s, p95 < 12 s | 7 days | Dominated by LLM; streaming hides it |
| Forecast freshness | champion trained on data ≤ 8 days old | continuous | Weekly CronJob + alert |
| Cost per agent answer | p95 < $0.05 | 7 days | `kairos_llm_cost_usd_total` / answers |

Error budget policy: if the agent burns > 50% of its monthly budget in a
week, feature work stops and the on-call fixes reliability first.

## Budgets enforced in code

| Budget | Where | Default |
|---|---|---|
| Agent max LLM steps | `Settings.agent_max_steps` | 6 |
| Agent token budget per question | `Settings.agent_token_budget` | 40k |
| SQL rows returned | `sql_guard.MAX_ROWS` | 200 (50 sent to the model) |
| Request body | pydantic `max_length` | 2,000 chars message |
| Rate limit | token bucket per API key; agent calls cost 5× | 120 units/min |
| LLM timeout / retries | `llm_timeout_s` / `llm_max_retries` | 60 s / 3 |

## Quality attributes

* **Reproducibility** – fixed seeds, data fingerprint in every manifest, deterministic FakeLLM in CI.
* **Testability** – every external dependency behind a protocol (`Warehouse`, `LLMClient`, `Embedder`, `Forecaster`).
* **Security** – least privilege (read-only tools), API keys compared in constant time and logged as hashes, PII redacted before logs/cache, non-root container.
* **Observability** – JSON logs with trace/span ids; Prometheus metrics for HTTP, LLM tokens/cost/latency, tool calls, cache hits.
* **Portability** – runs on a laptop (DuckDB, no services) and on K8s with the same image.
