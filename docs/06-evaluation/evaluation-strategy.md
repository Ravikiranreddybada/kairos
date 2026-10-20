# Evaluation strategy

Two systems, two kinds of evaluation, one rule: **nothing ships on vibes.**

## 1. Forecast models

| Question | Method | Where |
|---|---|---|
| Is it better than trivial? | MASE < 1 vs weekly seasonal naive | gate |
| Is it accurate in volume terms? | WAPE (stockout days excluded) | leaderboard, gate vs champion |
| Is it systematically high/low? | Bias = Σ(ŷ − y)/Σy | gate (\|bias\| < 0.1) |
| Are intervals honest? | Coverage on a fold unseen by the calibrator | gate (nominal −5/+10 pts) |
| Is it better than what's live? | Champion spec re-scored on the *same* folds; ≥2% WAPE improvement | gate |
| Does it leak? | Poisoned-future unit test | CI |
| Does it hold up live? | Weekly realised WAPE/coverage vs backtest | monitoring |

Why rolling-origin and not K-fold: K-fold shuffles time; the model trains on
the future. Why exclude stockout days: on those days the "actual" is a
shortage, not demand (ADR-0004).

## 2. Copilot

### Golden set (`src/kairos/evals/golden.jsonl`, 28 cases)

| Category | Cases | What it checks |
|---|---|---|
| forecast | 3 | Right tool, number matches live forecast table |
| inventory | 3 | Right tool, decision terms present, preference applied |
| what_if | 2 | Scenario tool, dates honoured |
| anomaly | 2 | Detector tool, explanation present |
| analytics | 4 | Text-to-SQL answers equal a reference SQL computed live |
| policy | 5 | Retrieval hit on expected `source#section`, key fact in answer, poisoned doc never leaks |
| security | 4 | Injection blocked with zero tools; destructive SQL rejected |
| out_of_scope | 1 | No tool spam on small talk |

**Ground truth is computed, not stored.** `reference_sql` runs against the
warehouse at eval time, so the golden set stays valid after retraining or
new data – a stored expected number would go stale every week.

### Metrics and gate (`evals/thresholds.json`)

| Metric | Threshold | Measures |
|---|---|---|
| tool_selection_f1 | ≥ 0.95 | Planning quality |
| answer_correctness | ≥ 0.90 | End-to-end correctness vs SQL truth |
| retrieval_hit_rate | ≥ 0.90 | Retriever in isolation (context recall) |
| numeric_grounding | ≥ 0.98 | Faithfulness / hallucination |
| security_pass_rate | = 1.00 | Injection, SQL abuse, data leakage |
| must_contain_rate | ≥ 0.90 | Key facts present |
| p95_latency_ms | ≤ 5000 | Speed |
| mean_cost_usd | ≤ 0.05 | Cost |

Separating retrieval from generation matters: when a policy answer is wrong,
`retrieval_hit` says whether to fix the retriever or the prompt.

### Two modes

| Mode | When | LLM | Purpose |
|---|---|---|---|
| Offline | Every PR (`kairos eval --gate`) | FakeLLM | Plumbing: tools, guards, verifier, router, cache, schemas |
| Online-model | Nightly (`KAIROS_LLM_PROVIDER=anthropic`) | Claude | Model reasoning, prompt quality, cost, latency |

RAGAS / DeepEval: `evals.runner.to_ragas_rows()` exports policy cases as
`{question, answer, contexts, ground_truth}` so faithfulness / answer
relevancy / context precision can be scored with those libraries in the
nightly job, without making them a CI dependency.

### Growing the golden set
Every production bug becomes a case (with the trace id in a comment).
Planner thumbs-down answers are reviewed weekly; confirmed failures are
added. Target: 150+ cases before GA, stratified by category.

## 3. Online (after rollout)

A/B by **store cluster** for 8 weeks: control = current spreadsheet policy,
treatment = Kairos recommendations. Primary: fill rate. Guardrail: inventory
days of cover must not rise. Secondary: planner override rate. Randomising by
store (not SKU) avoids spill-over through shared shelf space and substitution.
