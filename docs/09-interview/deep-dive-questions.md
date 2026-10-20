# Deep-dive questions and answers

### Forecasting

**Why not MAPE?** Undefined at zero and explodes on slow movers; it also
rewards under-forecasting. WAPE is volume-weighted (business view), MASE is
scale-free (cross-SKU view), bias catches systematic error.

**Your intermittent WAPE is 0.94. Isn't that bad?** For items that sell 0–2
units on most days, daily WAPE is dominated by timing noise. The decision for
those SKUs is a service-level buffer, so what matters is bias (GBM −8% vs ETS
−31%) and interval coverage. I'd report fill rate for that segment in production.

**How do you know there's no leakage?** By construction (all lags ≥ H) and by
test: poison every target after t − H, rebuild features, assert features at t
are unchanged. Plus rolling-origin evaluation only.

**Why a global model?** 48 series × 700 days is too little per series for
trees but plenty in aggregate; a promo effect learned on one SKU transfers.

**Why not ARIMA?** Damped ETS covers the same ground (level/trend/season) for
daily retail and is more robust automatically. ARIMA would be one more
`Forecaster` – the leaderboard would decide, and the code is built for that.

**What does conformal guarantee here, and when does it break?** Marginal
coverage ≥ 1−α if calibration and test residuals are exchangeable. Regime
shifts break it – hence online coverage monitoring and recalibration on every retrain.

**Why reconcile?** Coherence (store = Σ SKUs) is a trust requirement, and
reconciliation often *improves* accuracy by borrowing the smoother upper-level signal.

### Inventory

**Why include lead-time variance?** Var(lead-time demand) = L·σ_d² + d²·σ_L².
For a 40/day item with σ_L = 2 days the second term is 6,400 vs 1,008 – 86% of
variance. Ignoring it under-stocks the unreliable suppliers.

**Why not optimise orders directly with RL?** No trusted simulator, poor
explainability, and the closed-form policy is near-optimal for single-echelon
with known costs. RL would be a research project, not a client deliverable.

### LLM / agent

**How do you stop hallucinated numbers?** Three layers: tools are the only
source of numbers (prompt), the verifier checks every number > 31 against tool
outputs and forces one revision, and ungrounded answers carry a warning and are
never cached. It's measured as `numeric_grounding` in the gate.

**Why a graph, not a ReAct agent?** Budgets, guards, caching and verification
are code, not prompt text – testable and not talk-around-able.

**How does routing work, and how would you improve it?** Regex heuristics on
intent words and entity count. Next: log (question, tier, outcome), then train
a small classifier – or use the fast tier itself as the router – and evaluate
it on the golden set by cost at equal correctness.

**Prompt caching – what breaks it?** Any byte change in the prefix: timestamps
or user preferences in the system prompt, unsorted tool lists. We keep the
system prompt frozen, sort tools, and put preferences in the user turn.

**Why FakeLLM in CI? Isn't that cheating?** It tests the system (tools,
routing, guards, verifier, retrieval) deterministically and for free on every
PR. Model quality is tested nightly with the real model. Different questions,
different tests.

**What if the provider is down?** SDK retries; then `LLMUnavailable` → the
graph plans tools deterministically and returns tool results with a banner.
Planners still get numbers.

**Prompt injection via documents?** Sanitised at index time, flagged
untrusted, "data not instructions" in the system prompt – and the decisive
control: no write tools, so a successful injection can only produce a wrong
answer that the verifier and the planner can still catch.

### Systems

**Scale to 1M series?** Training: partition by category/region, Ray for local
models, block-diagonal reconciliation. Serving: unchanged (table reads).
Shared state (rate limits, memory, cache) to Redis; DuckDB → Postgres/Snowflake.

**What would you do next with two more weeks?** (1) Real-data connector +
dbt; (2) newsvendor on the full predictive distribution with quantile
conformal; (3) nightly real-model eval with 150 cases and RAGAS faithfulness;
(4) human-approved purchase-order drafts with audit log.

**What is the weakest part today?** Demand unconstraining is a simple
imputation; the router is heuristic; hashing embeddings won't scale past a
small corpus. All three are behind interfaces and on the roadmap.
