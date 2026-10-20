# Problem statement

## The business problem

A retail/CPG client runs ~N stores × M SKUs. Every week, planners decide what
to order from each supplier. Two failure modes cost money in opposite
directions:

| Failure | Cost | Typical size |
|---|---|---|
| **Stockout** – shelf empty | Lost margin, lost customer, penalty with retail partners | 4–8% of revenue in grocery |
| **Overstock** – too much stock | Working capital, holding cost (~25%/yr), spoilage, markdowns | 20–30% of inventory value is excess in many networks |

Today planners use spreadsheets with a moving average and a fixed "2 weeks of
cover" rule. This ignores seasonality, promotions, festivals and – most
expensively – **uncertainty**: an SKU with stable demand and a reliable
supplier needs far less buffer than a volatile SKU from a late supplier, but
both get "2 weeks".

## Why this is harder than "train a model"

1. **Censored demand.** On stockout days we observe *sales*, not *demand*. A
   model trained on raw sales learns that empty shelves mean low demand and
   under-forecasts exactly the items that ran out – a self-reinforcing loop.
2. **Point forecasts are not decisions.** Safety stock depends on the
   *spread* of the forecast error and on supplier lead-time variance. A model
   that is "accurate on average" can still give terrible orders.
3. **Intermittent demand.** Slow movers are zero most days; MAPE is
   undefined, ETS over-forecasts, and they need their own method.
4. **Hierarchy.** Planners read total → store → SKU. Independent forecasts at
   each level do not add up, and incoherent numbers destroy trust.
5. **Trust and adoption.** A planner will not act on a number they cannot
   question. The system must explain itself and never invent numbers.
6. **Policy lives in documents.** Service-level targets, supplier penalties,
   escalation rules are in PDFs and wikis, not in the database.

## Users

| Persona | Needs | Channel |
|---|---|---|
| Store / category planner | "What should I order for S01 this week, and why?" | Copilot chat (mobile), API-driven dashboards |
| Supply planning lead | Model quality, service level vs. cost trade-off | Model card, `/v1/model`, Grafana |
| Data scientist | Reproducible experiments, safe promotion of models | CLI, registry, eval reports |
| Other agents / tools | Call forecasting and policy as tools | MCP server |
| Platform engineer | Operate it, scale it, debug it | Metrics, traces, runbooks |

## What Kairos does

1. **Probabilistic demand forecasting** – 4 model families + ensemble,
   rolling-origin backtesting, per-segment selection, conformal prediction
   intervals with measured coverage, hierarchical reconciliation.
2. **Inventory optimisation** – safety stock with combined demand + lead-time
   variance, reorder point, EOQ/MOQ-aware order quantity, stockout
   probability, service-level cost curve.
3. **Scenario simulation** – promotion what-if with uplift and post-promo dip.
4. **Anomaly detection** – robust, explainable, with known-cause attribution.
5. **Grounded copilot** – LangGraph agent over 8 typed tools, hybrid RAG on
   policy documents, text-to-SQL behind an AST guard, numeric grounding
   verifier, semantic cache, cost-aware model routing, graceful degradation.
6. **Interop** – the same tools over REST and MCP.
7. **MLOps/LLMOps** – model registry with promotion gates, data contracts,
   CI eval gate, Prometheus metrics, structured traces, Docker/K8s.

## Out of scope (v1)

* Placing orders in an ERP (the copilot is read-only by design – ADR-0012).
* Multi-echelon optimisation (DC → store); designed for, not built (see roadmap).
* Price optimisation.
