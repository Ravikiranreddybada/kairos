# Current results

Default dataset: 4 stores × 12 SKUs × 730 days (seed 7), horizon 28, 3
backtest folds. Reproduce: `make seed train eval`. Numbers are identical on
macOS (Python 3.14) and in the Linux Docker image (Python 3.12).

## Forecast leaderboard (backtest, stockout days excluded)

| Model | WAPE reg. | WAPE interm. | MASE reg. | MASE interm. | Bias reg. | Bias interm. |
|---|---|---|---|---|---|---|
| seasonal_naive | 0.528 | 1.097 | 1.138 | 0.996 | +0.077 | −0.067 |
| croston_tsb | 0.385 | 0.960 | 0.823 | 0.874 | +0.043 | −0.050 |
| ets | 0.352 | 0.959 | 0.759 | 0.871 | −0.058 | −0.311 |
| ensemble (ETS+GBM) | 0.326 | 0.950 | 0.707 | 0.864 | −0.029 | −0.196 |
| **lightgbm** | **0.322** | **0.941** | **0.700** | **0.857** | **−0.001** | **−0.082** |

Segments are data-driven (ADR-0013): 40 series smooth, 8 intermittent by ADI/CV².
The generator's `is_intermittent` label is no longer read or used as a feature.

Champion (both segments): LightGBM. Overall WAPE **0.324**, MASE **0.726**,
bias **−0.1%**, 80% interval empirical coverage **82.8%** (held-out fold).

Reading the table: GBM's WAPE gain over ETS (−8% relative) is real, but the
bigger win is **bias**: ETS under-forecasts slow movers by 31%, which would
drive systematic stockouts on those SKUs. The ensemble does not beat GBM
here because ETS's bias drags it down.

## Gates for the champion run

| Gate | Result |
|---|---|
| data_quality | pass |
| interval_calibration | 0.828 vs 0.80 nominal – pass |
| beats_naive | MASE 0.726 < 1 – pass |
| bias | 0.001 < 0.10 – pass |
| beats_champion | first run – pass. Identical retrain → **blocked** (as designed) |
| significant_improvement | only with a champion: one-sided Diebold–Mariano p < 0.10 (ADR-0014). Identical retrain → p = 1 → **blocked** |

## Anomaly detector (vs 77 injected anomalies)

| Threshold | Precision | Recall | F1 |
|---|---|---|---|
| 4.0 | 0.45 | 0.62 | 0.53 |
| **5.0** | **0.77** | **0.62** | **0.69** |
| 6.0 | 0.94 | 0.57 | 0.71 |

## Copilot (offline gate, 28 cases)

| Metric | Value | Threshold |
|---|---|---|
| tool_selection_f1 | 1.00 | ≥ 0.95 |
| answer_correctness | 1.00 | ≥ 0.90 |
| retrieval_hit_rate | 1.00 | ≥ 0.90 |
| numeric_grounding | 1.00 | ≥ 0.98 |
| security_pass_rate | 1.00 | = 1.00 |
| must_contain_rate | 1.00 | ≥ 0.90 |
| p95 latency | 287 ms | ≤ 5000 ms |

Honesty note: offline scores are with FakeLLM and test the *system*
(routing, tools, guards, verifier, retrieval). They are an upper bound on
plumbing quality, not a measurement of Claude's reasoning; the nightly
real-model run measures that and is expected to score lower on
tool_selection_f1 and must_contain_rate, which is what the thresholds are for.

## Engineering checks

| Check | Result |
|---|---|
| Tests | 50 passed (unit + integration) |
| ruff | clean |
| mypy (pydantic plugin) | clean, 43 files |
| Docker | builds; container smoke test seed → train → serve → chat passes |
| SQL guard | 12/12 attack queries blocked |
