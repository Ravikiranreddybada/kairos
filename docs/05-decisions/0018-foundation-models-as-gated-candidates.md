# ADR-0018: Time-series foundation models are gated candidates, not defaults

Status: Accepted · Date: 2026-10-18 · Extends ADR-0008, ADR-0014

## Context

Pretrained zero-shot forecasters (Chronos-Bolt, TimesFM 3, Moirai) are now
strong and cheap to run on CPU. They help most where we are weakest: short
histories and new SKUs. They cannot see retail drivers (promotion, price,
festival), and their accuracy on *our* data is unknown.

## Decision

* `forecasting/foundation.py::FoundationForecaster` implements the normal
  `Forecaster` protocol. With `KAIROS_FOUNDATION_MODEL=chronos` and the
  `foundation` extra installed, the pipeline adds it to the backtest.
* It competes per segment on the same rolling-origin folds, gets conformal
  intervals, and must pass every gate including Diebold–Mariano. If it never
  wins, it never ships.
* Context is uncensored demand (ADR-0004). The predictor is injectable; CI
  uses a stub and never downloads weights. A missing package logs a warning
  and skips the candidate – training never fails on it.

## Consequences

+ We get the upside of foundation models with zero trust assumptions.
+ Swapping Chronos for TimesFM is one `Predictor` function.
− Torch is a heavy optional dependency; the default image does not include it.
− What-if and SHAP explanations still come from the GBM, even when a
  foundation model serves a segment (the `explain` note says so).

## Alternatives

Replace the model zoo with one foundation model: rejected – no promo/price
response, no what-if. Fine-tune: deferred until backtests show zero-shot wins.
