# ADR-0019: Monte-Carlo supply twin for stress tests and distribution-free reorder points

Status: Accepted · Date: 2026-10-18 · Extends ADR-0001

## Context

The closed-form (s, S) policy answers "what is the reorder point" under a
Normal approximation. Planners ask other questions: *what if the supplier is
7 days late, what if demand runs 30% hot, how many sales would we lose?* The
Normal approximation is also poor for intermittent and skewed demand.

## Decision

`inventory/simulate.py` simulates N seeded paths (default 2 000) through the
same policy: gamma-Poisson daily demand with the conformal forecast's mean and
variance, gamma lead times (+ scenario delay), lost sales, existing open order
arriving inside its lead time. It reports the outcome *distribution* (chance
of a stockout day in the horizon, fill rate, lost units p50/p90, ending stock
p10/p50/p90) as-is and under the scenario, and a distribution-free reorder
point (service-level quantile of simulated lead-time demand). Exposed as the
read-only tool `simulate_supply_risk`, `POST /v1/inventory/stress-test` and
`kairos stress`.

## Consequences

+ Answers disruption questions with numbers that come from a tool (grounded).
+ Seeded → same question, same answer → cacheable and auditable.
+ Unit tests check monotonicity (more delay → lower fill rate) and that the
  quantile ROP tracks the Gaussian ROP on well-behaved demand.
− ~30–150 ms per call at 2 000 paths; tunable via `KAIROS_SIMULATION_PATHS`.
− The "chance of a stockout day in 28 days" is a different number from the
  cycle stockout probability of `inventory_policy`; answers name it plainly.
