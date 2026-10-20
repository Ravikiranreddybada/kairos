# ADR-0006: Split-conformal prediction intervals

Status: Accepted · Date: 2026-10-18

## Context

Inventory policy needs forecast uncertainty. Point models (ETS, GBM) give none or give model-specific, often over-confident intervals. We need intervals that are (a) model-agnostic, so model selection can change freely, and (b) measurably calibrated.

## Decision

Split-conformal on out-of-fold backtest residuals, normalised by each series' MASE scale, with a separate quantile per horizon week and the finite-sample (n+1) correction. Coverage is measured on the last fold with the calibrator fitted on earlier folds only, and is a promotion gate (nominal −5 / +10 pts).

## Consequences

+ Works for every model and the ensemble; ~60 lines; guarantee under exchangeability.
+ Current: 80% nominal → 83.4% empirical (slightly conservative, which is the safe side for stockouts).
− Exchangeability is violated by regime changes (e.g. a new promotion strategy); online coverage monitoring catches it.
− Symmetric intervals; asymmetric/quantile conformal is a natural next step for skewed slow movers.

## Alternatives considered

Quantile GBM (3 models; quantile crossing; GBM-only); bootstrap residual simulation (slow); parametric Gaussian (wrong for counts).
