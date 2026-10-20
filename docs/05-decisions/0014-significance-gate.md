# ADR-0014: Diebold–Mariano significance gate for promotion

Status: Accepted · Date: 2026-10-18 · Extends ADR-0008

## Context

ADR-0008 promotes a challenger when its WAPE beats the champion's by 2% on the same folds. Three folds × 28 days is a small sample; a 2% gain can be noise. Promoting noise churns forecasts and planner trust for nothing.

## Decision

When a champion exists, also require a one-sided Diebold–Mariano test (HAC variance, Harvey–Leybourne–Newbold small-sample correction, Student-t reference; `statsmodels.tsa.stattools.diebold_mariano_test`) on the daily loss differential, p < 0.10. Panel → series: per date, sum absolute errors over all store × SKU series (volume-weighted, like WAPE). Result stored as `significance_vs_champion` in the manifest. A champion this code cannot serve (feature skew, ADR-0017) is not a baseline: `beats_champion` passes with reason "champion unservable".

## Consequences

+ Promotion needs evidence. Tested: clearly better → p < 0.01; equal → p > 0.05; worse → p > 0.95; identical → p = 1.
+ Uses a maintained implementation, not hand-rolled statistics.
− Daily aggregation ignores cross-series correlation structure; fine for a gate, not for a paper.
− With few folds, a real but small gain may wait for more data before it ships. That is the intended trade.

## Alternatives considered

Bootstrap CI on WAPE difference (comparable, slower, more code); larger fixed margin (rejected: margin size is arbitrary and scale-dependent).
