# Risk register

Scored Likelihood × Impact (1–3 each). Reviewed at every milestone.

| ID | Risk | L | I | Score | Mitigation (built) | Residual / owner |
|---|---|---|---|---|---|---|
| R1 | **Target leakage** inflates backtest, model fails in prod | 2 | 3 | 6 | Horizon-safe lags by construction; poisoning leakage test; rolling-origin CV only | Low – DS |
| R2 | **Censored demand** biases forecasts down after stockouts | 3 | 3 | 9 | Stockout days masked from targets *and* lag features; excluded from metrics | Medium: no explicit demand imputation model yet – DS |
| R3 | **Mis-calibrated intervals** → wrong safety stock | 2 | 3 | 6 | Conformal with held-out coverage check; calibration is a promotion gate | Low – DS |
| R4 | **Silent model regression** after retrain | 2 | 3 | 6 | Champion re-scored on same folds; 2% improvement margin; rollback command | Low – MLE |
| R5 | **Hallucinated numbers** in copilot answers | 3 | 3 | 9 | Tools-only numbers rule; numeric grounding verifier + revision; warning banner if still ungrounded; eval metric gated | Medium: semantic errors with correct numbers still possible – AI eng |
| R6 | **Prompt injection** (direct and via documents) | 3 | 3 | 9 | Input screening, doc sanitising at index time, docs marked untrusted, system prompt treats tool output as data, read-only tools | Medium: pattern lists are bypassable; read-only design caps the blast radius – AI eng |
| R7 | **SQL abuse** (exfiltration, DoS, writes) | 2 | 3 | 6 | AST guard: single SELECT, allow-listed tables, blocked functions, forced LIMIT | Low; add statement timeout + read replica in prod – Platform |
| R8 | **LLM cost runaway** | 2 | 2 | 4 | Step + token budget, cheap-model routing, semantic cache, prompt caching, per-key weighted rate limit, cost metric | Low – AI eng |
| R9 | **LLM provider outage** | 2 | 2 | 4 | SDK retries, typed errors, degraded mode answering from tools deterministically | Low – Platform |
| R10 | **Stale cache** returns answers about an old model | 2 | 2 | 4 | Cache key includes champion `run_id`; TTL | Low |
| R11 | **Synthetic data ≠ real data** | 3 | 2 | 6 | Generator encodes real pathologies; contracts + backtests rerun unchanged on real data via the `Warehouse` seam | Medium – first client data drop is the real test |
| R12 | Planner **does not trust** the system | 2 | 3 | 6 | Rationale strings, intervals, run_id on every number, citations, model card | Medium – product |
| R13 | Single-node DuckDB limits scale | 1 | 2 | 2 | `Warehouse` interface; scaling plan to Postgres/Snowflake | Low |
