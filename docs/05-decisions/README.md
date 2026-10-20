# Architecture Decision Records

Format: context → decision → consequences (good and bad) → alternatives.
An ADR is never edited after acceptance; a new ADR supersedes it.

| # | Decision | Status |
|---|---|---|
| [0001](0001-decision-first-scope.md) | Optimise for decisions, not forecast accuracy alone | Accepted |
| [0002](0002-single-tool-registry-mcp.md) | One tool registry for agent, MCP and API | Accepted |
| [0003](0003-duckdb-behind-warehouse-seam.md) | DuckDB behind a `Warehouse` seam | Accepted |
| [0004](0004-censored-demand.md) | Treat stockout days as censored demand | Accepted |
| [0005](0005-horizon-safe-direct-forecasting.md) | Horizon-safe lags + direct multi-horizon GBM | Accepted |
| [0006](0006-conformal-intervals.md) | Split-conformal prediction intervals | Accepted |
| [0007](0007-batch-train-online-serve.md) | Batch training, read-only serving (CQRS) | Accepted |
| [0008](0008-registry-promotion-gates.md) | File registry with champion/challenger gates | Accepted |
| [0009](0009-vendor-neutral-observability.md) | Vendor-neutral observability module | Accepted |
| [0010](0010-offline-eval-gate-fake-llm.md) | Deterministic FakeLLM eval gate in CI | Accepted |
| [0011](0011-hybrid-retrieval.md) | Hybrid BM25 + dense retrieval with RRF | Accepted |
| [0012](0012-explicit-agent-graph-read-only-tools.md) | Explicit agent graph, read-only tools | Accepted |
| [0013](0013-data-driven-demand-segmentation.md) | Data-driven ADI/CV² demand segmentation | Accepted |
| [0014](0014-significance-gate.md) | Diebold–Mariano significance gate for promotion | Accepted |
| [0015](0015-sql-sandbox-defense-in-depth.md) | Text-to-SQL sandbox in depth (allow-list, engine lock, timeout) | Accepted |
| [0016](0016-session-isolation.md) | Per-session isolation of preferences and cache | Accepted |
| [0017](0017-feature-schema-in-model-artifact.md) | Feature schema in model artifact; rollback re-serves forecasts | Accepted |
| [0018](0018-foundation-models-as-gated-candidates.md) | Time-series foundation models are gated candidates | Accepted |
| [0019](0019-monte-carlo-supply-twin.md) | Monte-Carlo supply twin and distribution-free reorder points | Accepted |
| [0020](0020-two-echelon-pooling.md) | Two-echelon pooling with measured correlation | Accepted |
| [0021](0021-human-sign-off-decision-ledger.md) | Human sign-off and a hash-chained decision ledger that learns | Accepted |
| [0022](0022-drift-and-doc-tree.md) | Calibrated drift monitoring and a navigable document tree | Accepted |
