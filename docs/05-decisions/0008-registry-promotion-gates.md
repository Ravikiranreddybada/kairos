# ADR-0008: File registry with champion/challenger promotion gates

Status: Accepted · Date: 2026-10-18

## Context

Retraining weekly must never silently ship a worse model. Comparing a new model's backtest WAPE with the champion's *old* WAPE is meaningless when the data window moved.

## Decision

Each run is written atomically to `registry/runs/<run_id>/` (manifest, booster, calibrator, data quality). The champion's *spec* is re-scored on the challenger's folds (same data, same windows). Gates: data quality, interval calibration, MASE < 1, |bias| < 0.1, WAPE ≤ champion × (1 − 2%). Promotion swaps a pointer file; rollback pops history. Runs mirror to MLflow when `MLFLOW_TRACKING_URI` is set.

## Consequences

+ Apples-to-apples comparison; tested that an identical retrain is *not* promoted.
+ Rollback in one command, no redeploy.
+ Audit trail: every number → run_id → data fingerprint, metrics, gates.
− File-based; for multi-team use, MLflow/SageMaker registry becomes the source of truth behind the same interface.

## Alternatives considered

Always promote latest (rejected: silent regressions); manual promotion only (rejected: does not scale weekly).
