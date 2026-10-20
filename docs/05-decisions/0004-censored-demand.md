# ADR-0004: Treat stockout days as censored demand

Status: Accepted · Date: 2026-10-18

## Context

When a shelf is empty, sales = stock, not demand. Training on raw sales teaches the model that stockouts mean low demand, so it under-forecasts, orders less, and causes more stockouts – a feedback loop.

## Decision

Stockout days are (1) excluded as training targets, (2) masked to NaN before computing lag/rolling features, (3) excluded from every accuracy metric, and (4) imputed by same-weekday recent mean for local models that cannot take NaNs.

## Consequences

+ Removes the downward bias at its source; models are scored against demand, not shortage.
+ Cheap; no extra model.
− Imputation for local models is simple; a proper censored-likelihood (Tobit-style) or demand-unconstraining model would be better and is on the roadmap.
− Requires a reliable stockout flag from the source system; contracts warn if the share exceeds 5%.

## Alternatives considered

Ignore (rejected: biased); treat as anomalies (rejected: they are not random); full censored regression now (deferred: complexity vs. data size).
