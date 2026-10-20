# ADR-0005: Horizon-safe lags and a direct multi-horizon GBM

Status: Accepted · Date: 2026-10-18

## Context

A GBM needs lag features. With lag-1 features, forecasting 28 days ahead needs recursion (feed predictions back as lags) – errors compound and train/serve features differ. Mixing short lags into a direct model leaks future targets into training.

## Decision

Every lag and rolling feature is shifted by at least the horizon H (28). One direct model predicts all H days at once. A unit test poisons all targets after t − H and asserts features at t are unchanged.

## Consequences

+ No recursion, no error compounding, train/serve parity by construction, leakage impossible.
+ One model instead of H.
− Gives up the most recent H days of signal for near horizons; for week-1 accuracy a horizon-specific model (H=7) can be added and blended – measured, then decided.

## Alternatives considered

Recursive forecasting (compounding errors, slow); one model per horizon step (28 models; better near-term accuracy; 28× training and ops).
