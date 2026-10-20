# API contracts

OpenAPI is served at `/docs` and `/openapi.json`. All `/v1/*` routes need
`X-API-Key`. Every response carries `x-trace-id` (send your own to correlate).

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/healthz` | Liveness | No auth, no dependencies |
| GET | `/readyz` | Readiness: a champion exists | 503 until first promotion |
| GET | `/metrics` | Prometheus exposition | Scrape-only; restrict at ingress |
| GET | `/v1/model` | Model card: spec, metrics, gates, data fingerprint, feature importance | |
| GET | `/v1/forecast/{store}/{sku}?horizon_days=1..28` | Daily forecast + interval + run_id | 404 unknown series |
| GET | `/v1/forecast/{store}/{sku}/explain?horizon_days` | Baseline + % effect per driver (TreeSHAP) | 503 if champion has no usable GBM |
| POST | `/v1/inventory/policy` | Reorder decision + service-level curve | 422 on invalid ids / CSL |
| GET | `/v1/inventory/worklist/{store}?service_level&top_k` | All SKUs at a store ranked by stockout risk | 404 unknown store |
| POST | `/v1/whatif/promo` | Promotion scenario | |
| POST | `/v1/inventory/stress-test` | Monte-Carlo policy stress test: as-is vs supplier delay / demand shock | Seeded, repeatable (ADR-0019) |
| GET | `/v1/inventory/network/{sku}?service_level&dc_to_store_days` | Store-direct vs DC pooled safety stock, verdict | 404 if < 2 stores (ADR-0020) |
| GET | `/v1/model/health?top_k` | Drift (PSI vs noise floor), level shift, retrain advice | ADR-0022 |
| POST | `/v1/decisions/proposals` | Freeze a policy recommendation as a PO proposal | 201; 409 if no order is recommended |
| GET | `/v1/decisions/proposals?store_id&sku_id&status&limit` | List proposals with hindsight scores | |
| GET | `/v1/decisions/proposals/{id}` | One proposal + its audit events | 404 unknown |
| POST | `/v1/decisions/proposals/{id}/approve` | Approve, optionally override `qty` (needs `reason`) (**approver key**) | 403 non-approver; 409 own proposal / already decided |
| POST | `/v1/decisions/proposals/{id}/reject` | Reject with reason (**approver key**) | as above |
| POST | `/v1/decisions/proposals/{id}/outcome` | Record realised demand → lessons | 409 unless approved, once only |
| GET | `/v1/decisions/lessons?store_id&sku_id` | Evidence-backed override lessons + value-add | ADR-0021 |
| GET | `/v1/decisions/audit/verify` | Recompute the SHA-256 hash chain | `ok:false` + `broken_at_seq` on tampering |
| GET | `/v1/anomalies?store_id&sku_id&limit&threshold` | Scored anomalies with explanations | |
| POST | `/v1/agent/chat` | Copilot turn | Rate-limit weight 5 |
| POST | `/v1/agent/chat/stream` | SSE: `node` events then `result` | `X-Accel-Buffering: no` for nginx |
| POST | `/v1/admin/train` | Start training in background (**admin key**) | 202; 403 planner key; 409 if already running |
| POST | `/v1/admin/rollback` | Previous champion + re-serve its forecasts (**admin key**) | 403 planner key; 409 no history / training running |

## Examples

```bash
curl -s -H 'X-API-Key: dev-key' 'localhost:8000/v1/forecast/S01/SKU002?horizon_days=7'
```
```json
{"store_id":"S01","sku_id":"SKU002","horizon_days":7,"total_units":279.3,
 "total_lo":118.4,"total_hi":440.1,"interval":"80%","model":"lightgbm",
 "run_id":"20261018T045047200368Z","daily":[{"date":"2026-10-01","yhat":38.57,"lo":15.59,"hi":61.55}, "..."]}
```

```bash
curl -s -H 'X-API-Key: dev-key' -H 'content-type: application/json' \
  -d '{"message":"Should we reorder SKU002 at S01?","session_id":"planner-7"}' \
  localhost:8000/v1/agent/chat
```
```json
{"answer":"For S01/SKU002 at 0.95 service level: reorder point 431.94, safety stock 152.68, inventory position 371.0 → order 520.0 units. Stockout probability 0.16.",
 "status":"ok","tier":"strong",
 "tool_calls":[{"name":"inventory_policy","input":{"store_id":"S01","sku_id":"SKU002"},"is_error":false,"latency_ms":9.8}],
 "citations":[],"grounding":{"score":1.0,"checked":4,"ungrounded":[],"passed":true},
 "usage":{"input_tokens":1543,"output_tokens":34,"cache_read_tokens":0,"cache_write_tokens":0},
 "cost_usd":0.0,"latency_ms":"…","trace_id":"…","data_version":"20261018T045047200368Z"}
```

`status` ∈ `ok | blocked | cached | degraded | budget_exhausted`. Clients
should show a subtle badge for `degraded` and `cached`.

## Error model

| Code | When |
|---|---|
| 401 | Missing/invalid API key |
| 404 | Unknown store/SKU |
| 409 | Training already running |
| 422 | Validation (pydantic) – body lists every bad field |
| 429 | Rate limited – `Retry-After` header |
| 503 | No champion model yet |
| 500 | Unhandled – body has `trace_id`; never a stack trace |

## Versioning

Additive changes (new fields, new endpoints) ship in `/v1`. Removing or
renaming a field, or changing meaning (e.g. interval width default) is a new
`/v2`; `/v1` stays for one deprecation cycle with a `Sunset` header.
