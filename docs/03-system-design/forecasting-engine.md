# Forecasting engine

Code: `src/kairos/forecasting/`.

## Pipeline

```
validate → backtest(all candidates) → leaderboard per segment → select
        → calibrate conformal → refit on full history → forecast H days
        → reconcile hierarchy → gates → register → promote → publish
```

Each step is a plain function, so Prefect/Airflow/ZenML can wrap them as
tasks without code changes.

## Candidate models

| Model | Type | Why it is in the pool | Known weakness |
|---|---|---|---|
| Seasonal naive (weekly) | Baseline | Defines MASE = 1; every model must beat it (gate) | No trend, no promo |
| Damped Holt-Winters (ETS) on log1p | Local, per series | Strong on smooth series; explainable trend/seasonality; good on aggregates | Cannot use promo/price covariates |
| Croston-TSB | Local, intermittent | Separates demand probability and size; decays for obsolete items | Flat forecast |
| LightGBM global, Tweedie | Global, cross-series | Learns promo/festival/price effects across all series; supports what-if | Needs feature care; leakage risk |
| Ensemble (ETS + GBM, equal weight) | Combination | Diversifies errors at zero training cost | Inherits ETS covariate blindness |

**Why Tweedie?** Daily unit sales are non-negative, right-skewed and have
many zeros. Tweedie (power 1.2, between Poisson and Gamma) models exactly
that; MSE would predict negative values and over-weight spikes.

**Why one global GBM rather than one per series?** 48 series × 700 days is
too little data per series for a tree model, but plenty in aggregate. A
global model shares strength (a promo effect learned on SKU008 helps SKU002).
This is the approach that won M5 (Walmart) forecasting.

## Features (horizon-safe – ADR-0005)

All lag and rolling features are shifted by ≥ H days:

| Feature | Definition |
|---|---|
| `lag_{H}`, `lag_{H+7}`, `lag_{H+14}`, `lag_364` | Demand H.. days ago |
| `roll_mean_{7,28,91}` | Rolling mean of the H-shifted series |
| `roll_std_28`, `roll_zero_share_28` | Volatility, intermittency |
| `dow_mean_8w` | Mean of the same weekday over 8 weeks, starting at the first same-weekday lag ≥ H |
| `dow, dom, month, doy_sin/cos, festival` | Calendar |
| `on_promo, promo_ended_3d, price_ratio` | Known-in-advance commercial plan |
| `store_id, sku_id, category, is_intermittent` | Categorical identity |

The trade-off: horizon-safe lags give up the most recent H days of signal
for short horizons. In exchange we get one model, no recursion, no error
compounding, and train/serve parity by construction. The leakage test
poisons all targets after `t − H` and asserts features at `t` are unchanged.

**Feature importance (gain, champion):** `dow_mean_8w` 0.31,
`roll_mean_28` 0.31, `sku_id` 0.12, `roll_zero_share_28` 0.08,
`roll_mean_91` 0.05, `price_ratio` 0.02, `on_promo` 0.01.

## Backtesting

Rolling origin, `n_folds` × H days, expanding window. Metrics exclude stockout
days (ADR-0004). The *same* out-of-fold predictions are used for (a) model
selection, (b) conformal calibration, (c) re-scoring the current champion for
the promotion gate – one source of truth, no double-dipping on the test fold
for coverage (calibrate on folds 0..k−1, measure on fold k).

## Selection

Per segment (regular, intermittent), lowest WAPE on backtest. Per-*series*
selection was rejected: with 3 folds × 28 days per series, the noise in a
per-series WAPE is larger than the gap between models, so per-series
selection overfits to luck.

## Prediction intervals (ADR-0006)

Split-conformal on scale-normalised absolute residuals:

```
score_i = |y_i − ŷ_i| / scale(series_i)        scale = in-sample MASE denominator
q_b     = quantile_{ceil((n+1)(1−α))/n}(scores in horizon bucket b)
interval = [max(0, ŷ − q_b·scale), ŷ + q_b·scale]
```

Buckets are horizon weeks (1–7, 8–14, …) because error grows with lead time.
Current: nominal 80%, empirical **83.4%** on the held-out fold.

## Hierarchical reconciliation

Base forecasts: bottom level from the champion, store and total from ETS
(aggregates are smooth – ETS is strong there). Reconciled with
WLS-structural: `ỹ = S (S'W⁻¹S)⁻¹ S'W⁻¹ ŷ`, `W = diag(S·1)`. Result:
every store total equals the sum of its SKUs, and the network total equals
the sum of stores (asserted in `test_hierarchy_is_coherent`). Bottom-up
and OLS are available for comparison.

## Results (default dataset)

| Model | WAPE regular | WAPE intermittent | MASE regular | Bias regular |
|---|---|---|---|---|
| seasonal_naive | 0.528 | 1.097 | 1.138 | +0.077 |
| croston_tsb | 0.385 | 0.960 | 0.823 | +0.043 |
| ets | 0.352 | 0.959 | 0.759 | −0.058 |
| ensemble | 0.327 | 0.950 | 0.709 | −0.031 |
| **lightgbm** | **0.323** | **0.941** | **0.702** | **−0.004** |

Champion: LightGBM for both segments. Overall WAPE 0.325, MASE 0.728,
bias −0.5%, coverage 0.834. Intermittent WAPE near 1 is expected (most days
are zero; WAPE is harsh there) – the decision metric for slow movers is
service level, not daily accuracy.

## What-if

Uses the champion GBM with a modified future promo plan (price −15%,
`on_promo = 1`) and compares against the baseline plan. Reports uplift, the
post-promo dip (`promo_ended_3d` effect) and **net** incremental units
(uplift minus dip), because gross uplift overstates promotion value – the
playbook requires netting pull-forward.
