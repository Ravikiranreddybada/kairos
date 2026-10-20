# CLAUDE.md – working in the Kairos repo

Kairos = supply-chain decision platform: probabilistic forecasting → inventory
policy → grounded LangGraph copilot, exposed over REST and MCP. Deep docs live
in `docs/` (start at `docs/README.md`); decisions in `docs/05-decisions/`.

## Commands

```bash
make setup            # .venv + all extras (dev, mcp, llm)
make seed train       # data → var/warehouse.duckdb, then train + promote a champion
make check            # ruff + mypy + pytest + eval gate  (exactly what CI runs)
.venv/bin/pytest -m "not slow" -q   # fast unit tests only
.venv/bin/kairos ask "Should we reorder SKU002 at S01?"
.venv/bin/kairos eval --gate        # golden-set gate; exits 1 on regression
```

`KAIROS_DATA_DIR` picks the state dir (default `var/`). Use a temp dir for experiments so you never clobber `var/`.

## Layout (dependencies point down only)

```
src/kairos/
  api/ mcp_server/ cli.py      delivery – thin; no business logic
  agent/                       graph.py (LangGraph), tools.py (THE tool registry), sql_guard.py, memory.py
  llm/ rag/                    client.py (Claude + FakeLLM), guardrails, cache, embeddings; hybrid retrieval + corpus/
  decisions/                   ledger.py: proposals, four-eyes sign-off, hash-chained audit, lessons (humans write via API only)
  forecasting/ inventory/ anomaly/   models, foundation, features, backtest, conformal, reconcile, registry, pipeline, service, monitor; policy, simulate (Monte-Carlo), network (DC pooling)
  data/                        synthetic generator, contracts, DuckDB warehouse
  config.py observability.py bootstrap.py   settings, logs/spans/metrics, composition root
```

`bootstrap.build()` is the only place concrete classes are wired. API, MCP, CLI and tests all use it.

## Invariants – do not break these

1. **No leakage.** Every lag/rolling feature is shifted by ≥ horizon (`features.lag_set`). `test_features_do_not_leak_future_target` must pass.
2. **Stockout days are censored demand**: masked in targets, lag features and metrics (`metrics.summarize`). Never score against them.
3. **Models ship only through gates** (`registry.evaluate_gates`). The champion is re-scored on the challenger's folds. Do not add a code path that writes `fact_forecast` outside `pipeline._publish` (rollback uses `publish_run`). Gates include a Diebold–Mariano test (ADR-0014). Segments come from data (`segmentation.py`), never from generator labels.
4. **Tools are read-only.** No tool may write data or call external side-effecting systems. The decision ledger is written only by `/v1/decisions/*` with human keys (approver ≠ proposer); `decision_history` only reads it.
   Never mutate the shared `ToolContext`; per-request values go through `Copilot._session_ctx` (ADR-0016).
5. **All LLM-written SQL goes through `sql_guard.guard`** and runs with `timeout_s`. Parse with sqlglot; never validate SQL with regex. The DuckDB engine is opened with external access off – do not turn it on (ADR-0015).
6. **Numbers in answers come from tools.** Keep the grounding verifier in the graph; don't cache ungrounded answers.
7. **One tool registry.** Add capabilities in `agent/tools.py::TOOLS`; mirror the signature in `mcp_server/server.py`.
8. **Prompt-cache stability.** `SYSTEM_PROMPT` stays byte-stable (no timestamps, no per-user data); tool definitions stay sorted; per-user preferences go in the user turn.
9. **Config only via `Settings`.** No `os.environ` reads outside `config.py` (exception: optional `MLFLOW_TRACKING_URI` mirror).

## Claude API usage (src/kairos/llm/client.py)

- Models: strong `claude-opus-5-5` (effort `high`), fast `claude-haiku-5-5` (effort `low`). Thinking is adaptive/always on – control depth with `output_config.effort`; never send `budget_tokens` or `thinking: disabled`.
- `tool_choice` must stay `{"type": "auto"}` – forced `any`/`tool` returns 400 on current models.
- In the tool loop append the full `response.content` (thinking blocks included) as the assistant turn.
- Strong tier sends `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`; always check `stop_reason == "refusal"`.
- Map SDK errors: `BadRequestError` → `LLMBadRequest` (bug); auth/429/5xx/connection → `LLMUnavailable` (graph degrades).

## Testing rules

- CI and tests use `FakeLLM` (`KAIROS_LLM_PROVIDER=fake`, default). Never require an API key in tests.
- New tool or agent behaviour → add golden cases to `src/kairos/evals/golden.jsonl` with `reference_sql` (computed truth) rather than hard-coded numbers, and a FakeLLM planning rule if needed.
- Integration tests share one trained session fixture (`tests/conftest.py`, 2 stores × 6 SKUs); keep golden questions that need S03/S04/SKU007+ out of the in-test gate (handled by id filtering).
- Do not lower `evals/thresholds.json` to make a change pass. Fix the change or write an ADR.

## Gotchas

- DuckDB is single-writer: stop the API before running `kairos train` on the same file (or use `POST /v1/admin/train`).
- pandas 3 defaults to string dtype – compare with `pd.api.types`, not `dtype == object`.
- `mcp` is 2.x: `from mcp.server.mcpserver import MCPServer` (FastMCP was renamed).
- `trace()` context is not safe across SSE generator threads – `Copilot.stream` creates its trace id directly.
- LightGBM on macOS needs `libomp` (`brew install libomp`).
- Changing GBM features makes the old champion's what-if/explain unavailable (skew guard) until `kairos train` promotes a new run.
- Admin routes (`/v1/admin/*`) need a key from `KAIROS_ADMIN_API_KEYS` (dev: `dev-admin-key`). Approve/reject needs `KAIROS_APPROVER_API_KEYS` (dev: `dev-approver-key`).
- Simulation is seeded (`settings.seed`): keep it that way, the cache and the eval rely on repeatable numbers.
- Foundation models are optional (`.[foundation]`, torch). Never import `chronos`/`torch` at module top level; tests inject a stub predictor.
- Logs go to stderr; CLI JSON results go to stdout.
