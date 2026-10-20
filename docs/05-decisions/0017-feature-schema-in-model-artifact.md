# ADR-0017: Feature schema travels with the model; rollback re-serves forecasts

Status: Accepted · Date: 2026-10-18 · Extends ADR-0008

## Context

Two lifecycle gaps. (1) The booster was saved without its feature list; serving rebuilt columns from *current* code. After a feature change the champion crashed LightGBM ("22 features vs 23") on what-if. (2) `rollback` flipped `champion.json` but `fact_forecast` kept the newer run's numbers – planners saw new forecasts labelled with the old run id.

## Decision

* `lightgbm_meta.json` stores `features`; prediction selects exactly those columns. On load, features this code cannot build mark the GBM unavailable with a clear reason ("retrain to restore what-if and explanations") instead of crashing; served forecasts keep working (they are precomputed).
* Each run saves `forecast.csv` + `hierarchy.csv` (what it would serve). `pipeline.rollback` restores the pointer **and** republishes that snapshot through the one writer `_publish` (`kairos rollback`, `POST /v1/admin/rollback`). Pointer writes are atomic for rollback too.
* Admin routes (train, rollback) need a key from `KAIROS_ADMIN_API_KEYS`; planner keys get 403.

## Consequences

+ Tested: rollback serves the previous run's rows; a stale-feature champion degrades cleanly and does not block a retrain.
− Snapshots cost disk (~1 MB per run at demo scale); prune old runs in production.
