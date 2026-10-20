# ADR-0001: Optimise for decisions, not forecast accuracy alone

Status: Accepted · Date: 2026-10-18

## Context

Most forecasting projects stop at a WAPE number. Planners do not act on WAPE; they act on order quantities. A model that is 2% more accurate but gives no uncertainty cannot set safety stock, and safety stock is where the money is (stockouts vs. working capital).

## Decision

Kairos's unit of value is a **decision with a rationale**: reorder point, safety stock, order quantity, stockout probability and the cost of alternative service levels. Forecasting is a component that must emit calibrated uncertainty. The copilot exists to make those decisions explorable, not to replace them.

## Consequences

+ Interval calibration becomes a first-class, gated metric.
+ Inventory maths (combined variance) and supplier data become part of the core model.
+ Every number carries a run_id and a rationale, which drives trust.
− More surface area than a pure forecasting repo; more to test.

## Alternatives considered

Pure forecasting service (rejected: does not answer "how much should I order"); end-to-end RL ordering policy (rejected: needs a simulator we trust and is not explainable to planners).
