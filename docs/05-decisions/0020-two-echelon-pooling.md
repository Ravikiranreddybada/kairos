# ADR-0020: Two-echelon pooling with measured correlation

Status: Accepted · Date: 2026-10-18

## Context

"Would a distribution centre (DC) cut our safety stock?" The textbook
square-root law assumes independent store demand and ignores the extra
DC → store leg, so it oversells pooling.

## Decision

`inventory/network.py` compares store-direct safety stock with a pooled DC
buffer plus small store-leg buffers. Pooled demand variance uses the measured
correlation of de-seasonalised daily demand between stores (stockout days
excluded). Lead-time variance does not pool (all units wait for the same
supplier). Output includes units and holding cost saved, the break-even DC →
store lead time, the lead-time-variance share and a plain verdict. Tool:
`network_pooling`; REST: `GET /v1/inventory/network/{sku}`.

## Consequences

+ Honest answers. On the default data a DC often *adds* buffer because
  supplier lead-time variance dominates; the tool says "fix the supplier first".
− Single SKU, single supplier, safety stock only (no cycle stock or transport
  cost). Full multi-echelon optimisation stays on the roadmap.
