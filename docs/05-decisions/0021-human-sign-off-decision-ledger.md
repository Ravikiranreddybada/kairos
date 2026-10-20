# ADR-0021: Human sign-off and a hash-chained decision ledger that learns

Status: Accepted · Date: 2026-10-18 · Keeps ADR-0012 (read-only tools)

## Context

A copilot that only answers questions stops short of the decision. Letting
the agent place orders breaks invariant 4 and is unsafe. Planners also
override recommendations all the time, and nobody measures if that helps.

## Decision

* `decisions/ledger.py` (SQLite, `var/decisions.sqlite`). A planner key
  **proposes** a purchase order: the full policy output and model run id are
  frozen. An **approver** key (`KAIROS_APPROVER_API_KEYS`) approves, rejects or
  overrides the quantity. Four-eyes rule: the proposer cannot decide their own
  proposal; an override needs a reason.
* Every event is appended to a SHA-256 hash chain; `GET
  /v1/decisions/audit/verify` recomputes it and names the first broken entry.
* Realised demand can be recorded per approved proposal. The ledger scores the
  model's and the planner's quantity against the hindsight-ideal order and
  keeps **lessons** per store/SKU: override direction and size, override
  value-add %, evidence count, decision ids and confidence. Lessons are
  recomputed from all evidence, so new outcomes refine them, never overwrite.
* The agent reads all of this through the read-only `decision_history` tool.
  Only humans write, through `/v1/decisions/*`.

## Consequences

+ Closes the loop recommend → decide → outcome → learn, with an audit trail
  regulators and finance accept.
+ Forecast value-add at the decision level: "your overrides on S01/SKU002
  improved order error by 40% (medium confidence, 5 outcomes)".
− SQLite is single-node; use Postgres (append-only table + same chain) for
  several replicas.
− Hindsight-ideal uses a simple target (demand + safety stock − position);
  an ERP feed of true needs would be better.
