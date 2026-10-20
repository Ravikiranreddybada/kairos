# Milestones and acceptance criteria

Every milestone has *testable* acceptance criteria. "Done" means the test
exists and passes in CI, not that the code was written.

## M0 – Walking skeleton
- [x] `src/` layout, `pyproject.toml`, ruff + mypy + pytest in CI.
- [x] Typed settings (`config.py`); no `os.environ` reads elsewhere.
- [x] Synthetic generator with seasonality, promos, festivals, censored stockouts, intermittent SKUs, labelled anomalies.
- [x] Data contracts: schema, nulls, negatives, grain uniqueness, calendar gaps, stockout share, history length.
- **Test:** `test_contracts_catch_bad_data`.

## M1 – Honest measurement
- [x] Rolling-origin folds (`make_folds`) – contiguous, non-overlapping.
- [x] WAPE, MASE, bias, sMAPE, pinball, coverage; stockout days excluded from scoring.
- [x] Horizon-safe features; leakage test that poisons future targets and asserts features are unchanged.
- **Tests:** `test_folds_are_contiguous_and_ordered`, `test_features_do_not_leak_future_target`, `test_summarize_excludes_stockout_days`.

## M2 – Probabilistic forecasting
- [x] Seasonal naive, damped ETS (per series, parallel), Croston-TSB, LightGBM Tweedie global, ETS+GBM ensemble.
- [x] Per-segment (regular / intermittent) champion selection.
- [x] Split-conformal intervals, scale-normalised, per horizon week; coverage measured on a fold the calibrator never saw.
- [x] Hierarchical reconciliation (OLS / WLS-structural / bottom-up).
- **Tests:** `test_conformal_achieves_nominal_coverage...`, `test_reconciliation_is_coherent...`, `test_hierarchy_is_coherent`.

## M3 – Decisions
- [x] (s, Q) policy with combined variance, EOQ, MOQ, stockout probability, rationale string.
- [x] Service-level trade-off curve.
- [x] Promotion what-if with post-promo dip and net incremental units.
- [x] Robust anomaly detector with promo / festival / stockout attribution; precision/recall on ground truth.
- **Tests:** `test_safety_stock_uses_combined_variance`, `test_anomaly_detector_finds_injected_anomalies`.

## M4 – Productionise models
- [x] File registry, atomic run publish, champion pointer with history, rollback.
- [x] Gates: data quality, interval calibration, beats naive, bias, beats champion on *same folds*.
- [x] Atomic publish of `fact_forecast` + `fact_forecast_hierarchy`.
- [x] FastAPI with auth, rate limits, trace ids, Prometheus.
- **Tests:** `test_retrain_without_improvement_is_not_promoted`, `test_registry_promote_and_rollback`, `test_api_end_to_end`.

## M5 – Copilot
- [x] 8 typed tools (incl. SHAP explain + store worklist), one registry for agent + MCP.
- [x] AST SQL guard (12 attack cases).
- [x] Hybrid BM25 + dense RAG with RRF; structure-aware chunking; indirect-injection sanitising.
- [x] LangGraph: guard → route → cache → llm ⇄ tools → verify → finalize.
- **Tests:** `test_sql_guard_blocks_attacks`, `test_hybrid_retrieval_and_poisoned_doc_is_sanitised`, `test_agent_answers_grounded_and_blocks_injection`.

## M6 – Trust at scale
- [x] Golden set (28 cases, 10 categories) with live-SQL ground truth.
- [x] Thresholds file + `kairos eval --gate` in CI.
- [x] Numeric grounding verifier with one revision loop.
- [x] Semantic cache keyed by model `run_id`.
- [x] Step/token budget; graceful degradation on provider outage.
- **Tests:** `test_eval_gate_passes`, `test_agent_degrades_gracefully...`, `test_agent_stops_at_step_budget`, `test_semantic_cache_...invalidates_on_new_run`.

## M7 – Operate
- [x] MCP server (stdio) with tools + resources.
- [x] Multi-stage Dockerfile (non-root, healthcheck), compose with Prometheus + Grafana.
- [x] K8s: Deployment + HPA + CronJob for training.
- [x] Docs: this folder.
- **Tests:** `test_mcp_server_exposes_same_tools`.
