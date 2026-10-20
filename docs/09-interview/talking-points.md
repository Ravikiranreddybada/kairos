# Presenting Kairos

## 30-second version
"Kairos turns sales history into inventory decisions. It backtests four
forecasting model families, picks the best per demand segment, wraps it in
calibrated conformal intervals, and turns those into reorder points that
account for supplier lead-time variance. On top sits a LangGraph copilot
over six typed tools – forecasts, policy, what-if, anomalies, guarded SQL and
hybrid RAG on policy docs – with a numeric-grounding verifier so it can't
invent numbers. Every PR runs a golden-set eval gate offline; models only
ship if they beat the champion on the same folds."

## 2-minute walk-through (follow the data)
1. **Problem**: stockouts vs overstock; planners use "2 weeks of cover". The money is in uncertainty, not average accuracy.
2. **Data**: synthetic, but with the real pathologies – censored stockouts, intermittent SKUs, moving festivals, promo pull-forward.
3. **Forecasting**: rolling-origin backtest; naive / ETS / TSB / Tweedie GBM / ensemble; horizon-safe features with a leakage test; GBM wins with WAPE 0.325, MASE 0.73, ~0 bias.
4. **Uncertainty**: split-conformal, scale-normalised, per horizon week; 80% nominal → 83% measured on a held-out fold; calibration is a promotion gate.
5. **Decision**: SS = z·√(Lσ_d² + d²σ_L²); lead-time variance is 86% of the variance for the example SKU – a demand-only formula would halve safety stock exactly where suppliers are unreliable.
6. **Copilot**: explicit graph; guard before tokens; cache keyed on model version; cheap/strong routing; tools validated; SQL parsed to AST; grounding verifier with one revision; degraded mode on outage.
7. **Ops**: registry with gates and rollback, Prometheus, JSON traces, Docker/K8s, MCP so other agents reuse the tools.

## Things that make it non-obvious (lead with these)
* Censored demand handled in targets, features *and* metrics.
* Champion re-scored on the challenger's folds – apples to apples; identical retrain is provably not promoted.
* Coverage measured on data the calibrator never saw.
* Hierarchy reconciled (WLS-structural), so dashboards add up.
* Cache invalidates on model promotion.
* Poisoned document in the corpus to prove indirect-injection handling.
* The eval caught a real routing bug during development.
* Read-only tools: injection worst case = wrong answer, never a wrong action.

## Mapping to the role

| JD item | Where in Kairos |
|---|---|
| Forecasting, classification, anomaly detection | forecasting/, anomaly/ |
| Time-series basics (trend, seasonality, ETS/ARIMA) | ETS damped Holt-Winters, MASE, seasonal naive |
| Tree models, CV, metrics, overfitting | LightGBM Tweedie, rolling-origin CV, per-segment (not per-series) selection |
| Statistics, hypothesis testing | Conformal guarantees, robust MAD scores, A/B design by store cluster |
| EDA, feature engineering, data quality | synthetic pathologies, features.py, contracts.py |
| RAG, embeddings, vector search | rag/index.py (hybrid + RRF) |
| Tool calling, agent loops, memory | agent/graph.py, tools.py, memory.py |
| LangGraph + an LLM API | LangGraph state machine + Claude SDK |
| Evaluate hallucination, latency, cost | evals/, grounding verifier, cost metrics |
| Package as APIs, deployment | FastAPI, Docker, K8s, CI |
| MLflow, Docker, FastAPI, cloud | Registry (MLflow mirror), Dockerfile, K8s manifests |
| MCP | mcp_server/ |
| Explain to non-technical stakeholders | Rationale strings, service-level cost curve, model card |
