# End-to-end build guide

How to build Kairos from an empty folder, in the order that keeps the system
working at every step. Each step ends with a command that must pass before you
go on. File references point at the finished implementation.

---

## Step 0 – Skeleton (½ day)
1. `pyproject.toml` with `src/` layout, ruff, mypy, pytest config.
2. `config.py`: one `Settings` class (pydantic-settings, `KAIROS_` prefix). Rule: no `os.environ` anywhere else.
3. `observability.py`: JSON logger, `trace()`, `span()`, Prometheus metrics.
4. CI workflow running lint + types + tests.

**Pass:** `make lint type test` green with one trivial test.

## Step 1 – Data you can trust (1 day)
1. `data/synthetic.py`: generate the pathologies first, not pretty curves (see data-model-and-flow.md table). Seed everything.
2. `data/contracts.py`: return a report, never raise; severity `ok|warn|error`.
3. `data/warehouse.py`: DuckDB behind a class; `load`, `query`, `sales`, `table`, thread lock.
4. CLI `kairos seed`.

**Pass:** `test_contracts_catch_bad_data`.

## Step 2 – Measure before you model (1 day)
1. `forecasting/metrics.py`: WAPE, MASE, bias, sMAPE, pinball, coverage; exclude stockouts in `summarize`.
2. `forecasting/backtest.py`: `make_folds` + `backtest(model, …)` returning out-of-fold rows with `h` and `fold`.
3. `SeasonalNaive` model only.

**Pass:** backtest prints a seasonal-naive WAPE (~0.53). This is the number to beat.

## Step 3 – Models (2 days)
1. `Forecaster` protocol: `fit(history, skus)`, `predict(history, future)`.
2. `ETSLocal` (log1p, damped, weekly season, joblib-parallel, naive fallback on failure).
3. `CrostonTSB`.
4. `features.py`: horizon-safe lags/rolls, calendar, festival, promo, price ratio; stockouts masked **before** lags. Write the leakage test *now*.
5. `LightGBMGlobal`: Tweedie; categories aligned between fit and predict.

**Pass:** `test_features_do_not_leak_future_target`; GBM WAPE < ETS WAPE < naive.

## Step 4 – Uncertainty and coherence (1 day)
1. `conformal.py`: series scales, per-horizon-week quantiles, finite-sample correction, `evaluate_coverage` on the last fold.
2. `reconcile.py`: summing matrix, OLS/WLS/bottom-up, long-format wrapper.

**Pass:** synthetic conformal test (coverage within 0.77–0.84), coherence test.

## Step 5 – Pipeline, registry, gates (1–2 days)
1. `registry.py`: atomic run dirs (write to `.tmp`, rename), champion pointer with history, rollback, gates.
2. `pipeline.py`: validate → backtest all → ensemble → leaderboard by segment → select → score champion spec on same folds → gates → calibrate → refit → forecast → reconcile → apply intervals → register → promote → publish in one transaction.
3. `kairos train`, `kairos rollback`.

**Pass:** first train promotes; an identical second train does **not** (`test_retrain_without_improvement_is_not_promoted`).

## Step 6 – Decisions (1 day)
1. `inventory/policy.py`: combined-variance SS, ROP, EOQ/MOQ, stockout probability, rationale, service-level curve.
2. `forecasting/service.py`: read published forecasts; build `PolicyInput` from forecast + supplier + inventory; what-if via the champion GBM with a modified promo plan; hot-reload on promotion.
3. `anomaly/detector.py`: robust score, attribution, `evaluate` vs truth.

**Pass:** closed-form SS test; detector precision ≥ 0.6 at threshold 5.

## Step 7 – API (1 day)
FastAPI with lifespan → `bootstrap.build()`; middleware for trace id + latency metric; API key + weighted token bucket; exception handlers mapping `NotReady→503`, `NotFound→404`.

**Pass:** `test_api_end_to_end` (minus agent routes).

## Step 8 – Language layer (2 days)
1. `llm/client.py`: `LLMClient` protocol; `AnthropicClient` (cached system block, sorted tools, `tool_choice=auto`, effort per tier, server-side fallback on strong tier, typed error chain, cost accounting); `FakeLLM` (plan from keywords, answer only from tool results).
2. `llm/embeddings.py`, `rag/index.py`: chunk by heading, sanitise, BM25 + dense + RRF.
3. `llm/guardrails.py`: injection regex, PII redaction, numeric grounding.
4. `llm/cache.py`: semantic cache keyed by data version.
5. `agent/sql_guard.py`: AST rules + tests for every attack.

**Pass:** `tests/unit/test_llm_safety.py`.

## Step 9 – Agent (2 days)
1. `agent/tools.py`: pydantic inputs, compact outputs, `execute()` that never raises.
2. `agent/memory.py`: turns + preferences.
3. `agent/graph.py`: nodes guard/cache/route/llm/tools/verify/finalize; budgets; degraded mode; stream.
4. API routes `/v1/agent/chat` and `/stream`.

**Pass:** grounded answer, blocked injection, degraded mode, budget stop tests.

## Step 10 – Evals and CI gate (1 day)
Golden JSONL with live `reference_sql`; runner computing tool F1, correctness, retrieval hit, grounding, security, latency, cost; thresholds JSON; `kairos eval --gate`; CI job.

**Pass:** gate green; then break something on purpose (e.g. change a tool description) and watch it fail.

## Step 11 – MCP, containers, docs (1–2 days)
MCP server over the same registry; Dockerfile (multi-stage, non-root, healthcheck); compose with Prometheus/Grafana; K8s manifests; docs + ADRs.

**Pass:** container smoke test (deployment.md); `test_mcp_server_exposes_same_tools`.

---

## Extending it

| You want to… | Touch | Don't forget |
|---|---|---|
| Add a model | `forecasting/models.py`, `pipeline._models` | It auto-enters the leaderboard; gates decide |
| Add a tool | `agent/tools.py` (+ MCP wrapper) | Golden-set cases; FakeLLM plan rule |
| Use real data | New `Warehouse` implementation | Contracts first; check stockout flag quality |
| Change the prompt | `agent/graph.py::SYSTEM_PROMPT` | Nightly real-model eval before/after; prompt cache resets once |
| Add a doc | drop `.md` into `rag/corpus/` | Add a policy eval case with `expected_sources` |
