# ADR-0022: Calibrated drift monitoring and a navigable document tree

Status: Accepted · Date: 2026-10-18 · Extends ADR-0011

## Context

(1) Between retrains nothing told planners whether a forecast was still
valid. Raw PSI on 28 daily points flagged 38 of 48 series – noise. (2) Chunk
search answers fact questions but not "what does this document cover?" or
"read me the whole section".

## Decision

* `forecasting/monitor.py`: PSI per series against the previous 182 days,
  compared with a per-series **noise floor** (95th percentile PSI of random
  28-day windows inside the reference). Level shift vs the published forecast
  counts only when material (> 25%) *and* > 2 standard errors. Only level
  shifts recommend a retrain; shape drift alone is "watch". Tool
  `model_health`, `GET /v1/model/health`, `kairos health`.
* `rag/tree.py`: a PageIndex-style tree (document → sections, extractive
  summaries, no LLM, no embeddings) exposed as `browse_docs`. Section text
  passes the same injection sanitiser as the hybrid index.

## Consequences

+ Drift alarms fell from 38 to 16 series, with 5 real level shifts on the default data.
+ The model can navigate documents by structure and cite `doc#Section`.
− Without logged past forecasts we cannot yet score realised accuracy per
  week; logging served forecasts is the next step.
