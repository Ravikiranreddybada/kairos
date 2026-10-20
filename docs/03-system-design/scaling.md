# Scaling

## Where load comes from

| Workload | Shape | Scales with |
|---|---|---|
| Training | Batch, CPU-heavy, weekly | series count × history × folds × models |
| Forecast / policy reads | Many small reads, latency-sensitive | users, dashboards, other agents |
| Copilot | Few, slow, expensive (LLM-bound) | active planners |

They are already **separated** (ADR-0007): training is a job that writes
tables; the API only reads. Each scales independently.

## From this repo to 1M series

Current: 48 series, full train (4 models × 3 folds + refit + reconcile) ≈ 25 s on a laptop.

| Scale | Series | Changes |
|---|---|---|
| Pilot | 10³ | None. DuckDB file on a volume; 1 API replica. |
| Region | 10⁴–10⁵ | Warehouse → Postgres/Snowflake. Registry → S3 + MLflow. Training on a 32-core node: ETS is embarrassingly parallel (joblib already), LightGBM is multi-threaded. Partition the GBM by category if one model gets too large. |
| National | 10⁶ | Ray/Dask/Spark for local models (one task per series batch). GBM trained per category/region partition. Reconciliation per hierarchy subtree (S is block-diagonal → solve per store, not one 10⁶×10⁶ system). Forecast table partitioned by date, clustered by store. |

Reconciliation cost note: the WLS solve is on `S'W⁻¹S` (n_bottom × n_bottom).
Never form it densely at scale – exploit that it is block-structured per
store, or use bottom-up + MinT-shrink per subtree.

## API tier

* Stateless pods behind a load balancer; HPA on CPU (manifest in `infra/k8s`).
* State that must be shared across replicas moves out of process:
  * rate-limit buckets → Redis (Lua token bucket);
  * session memory → Redis/Postgres (interface already isolated in `Memory`);
  * semantic cache → Redis with vector search or pgvector;
  * DuckDB → Postgres read replica.
* Model hot-reload: `ForecastService` checks the champion pointer per request
  and reloads the GBM when it changes – no restart on promotion.

## Copilot tier

LLM latency, not CPU, bounds throughput. Levers in order of impact:

1. **Don't call the LLM** – semantic cache (hit rate is high: planners ask
   the same Monday questions), and direct API endpoints for dashboards.
2. **Cheaper calls** – route lookups to the fast tier; prompt-cache the
   frozen system prompt + tools; compact tool payloads.
3. **Fewer calls** – parallel tool use in one turn; step budget.
4. **Concurrency** – the graph runs in a thread pool; move to the async
   Anthropic client + `ainvoke` when concurrency per pod > ~50.
5. **Back-pressure** – weighted rate limits (agent calls cost 5 units) and a
   provider-level concurrency semaphore to stay under the org rate limit.

Capacity sketch: 2,000 planners × 15 questions/day ≈ 30k questions/day ≈
1 question/s peak-hour. At ~1.5 LLM calls/question, 4 s each, that is ~6
concurrent LLM calls – trivial for 2 pods. Cost at a 40% cache-hit rate,
70% fast tier: well under the $0.05/question SLO.

## Batch forecasting vs on-demand

We publish all forecasts weekly (and could daily). On-demand inference is
used only for what-if, where the input is user-defined. Batch wins because
reads are O(1), the model never sits in the request path, and every number
a planner sees on a given day is identical across channels (dashboard =
API = copilot = MCP).
