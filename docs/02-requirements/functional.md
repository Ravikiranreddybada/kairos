# Functional requirements

IDs are referenced by tests and ADRs.

## Forecasting
| ID | Requirement |
|---|---|
| F-FC-1 | Daily forecasts for every store × SKU for a 28-day horizon. |
| F-FC-2 | Each forecast carries an 80% prediction interval (configurable alpha). |
| F-FC-3 | Forecasts at total and store level equal the sum of their children (coherent). |
| F-FC-4 | Model selection is automatic and per segment (regular vs intermittent). |
| F-FC-5 | Every published number is traceable to a `run_id` with data fingerprint, metrics and gates. |
| F-FC-6 | Training refuses to run on data that fails contracts. |
| F-FC-7 | A new model is promoted only if it passes all gates; otherwise the champion keeps serving. |
| F-FC-8 | Operators can roll back to the previous champion with one command. |

## Inventory & scenarios
| ID | Requirement |
|---|---|
| F-INV-1 | For a store × SKU and service level, return safety stock, reorder point, inventory position, order decision and quantity. |
| F-INV-2 | Safety stock must include supplier lead-time variability (policy doc v3.2). |
| F-INV-3 | Return the cost of alternative service levels (90/95/98/99%). |
| F-INV-4 | Simulate a promotion: baseline vs promo units, uplift, post-promo dip, net incremental. |
| F-AN-1 | List anomalies with score, expected value and an explanation; attribute known causes. |

## Copilot
| ID | Requirement |
|---|---|
| F-AG-1 | Answer natural-language questions using tools; every figure must come from a tool. |
| F-AG-2 | Answer policy questions from documents with `source#section` citations. |
| F-AG-3 | Answer ad-hoc analytical questions via read-only SQL. |
| F-AG-4 | Refuse instruction-override / prompt-extraction attempts without calling tools. |
| F-AG-5 | Never execute non-SELECT SQL or touch non-allow-listed tables/files. |
| F-AG-6 | Remember per-session context and stated preferences (e.g. target service level). |
| F-AG-7 | Stream progress (tool calls) to the client. |
| F-AG-8 | Keep working (degraded) when the LLM provider is unavailable. |

## Interfaces
| ID | Requirement |
|---|---|
| F-IF-1 | REST API under `/v1` with OpenAPI docs. |
| F-IF-2 | MCP server exposing the same tools + schema and model-card resources. |
| F-IF-3 | CLI for seed / train / ask / eval / serve / mcp / rollback. |
