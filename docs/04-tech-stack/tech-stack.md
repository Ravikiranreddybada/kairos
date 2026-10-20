# Tech stack

Rule for every dependency: it must solve a problem we actually have, and it
must sit behind a seam so it can be replaced.

| Layer | Choice | Why it won | Alternatives considered | Swap seam |
|---|---|---|---|---|
| Language | Python 3.11+ (tested on 3.12 in Docker, 3.14 locally) | ML ecosystem; one language end to end | — | — |
| Data frames | pandas 2/3, NumPy | Ubiquitous; enough for 10⁵ rows | Polars (faster; less library interop) | — |
| Warehouse | **DuckDB** | Columnar SQL in-process, zero ops, fast for analytics | SQLite (row store, slow aggregates), Postgres (needs a server for a demo) | `Warehouse` class |
| Stats models | **statsmodels** Holt-Winters | Mature, damped trend, robust | statsforecast (faster, numba dependency), Prophet (slow, weaker on daily retail) | `Forecaster` protocol |
| ML model | **LightGBM** (Tweedie) | Best tabular accuracy/speed; native categoricals; M5 winner family | XGBoost (similar; slower categorical handling), deep models (N-BEATS/TFT – more data, GPU, less explainable) | `Forecaster` |
| Intervals | Split-conformal (own, ~60 lines) | Model-agnostic, guarantee, measurable | Quantile GBM (3 models, can cross), bootstrapping (slow) | `ConformalCalibrator` |
| Optimisation maths | SciPy `norm` | Closed-form policy needs only Φ / Φ⁻¹ | OR-Tools (needed only for multi-echelon / MOQ bundles) | — |
| Agent orchestration | **LangGraph** | Explicit state machine, conditional edges, streaming, small surface | LangChain AgentExecutor (opaque loop), CrewAI/AutoGen (multi-agent we don't need), hand-written loop (fine, but less inspectable) | `Copilot` |
| LLM | **Claude** via official `anthropic` SDK: `claude-opus-5-5` (strong), `claude-haiku-5-5` (fast) | Strong tool use; prompt caching; adaptive thinking with effort control; server-side refusal fallback | Any provider behind `LLMClient` | `LLMClient` protocol |
| Offline LLM | **FakeLLM** (own) | Deterministic CI gate with no key and no cost | Recorded cassettes (brittle when prompts change) | `LLMClient` |
| SQL safety | **sqlglot** | Real parser for DuckDB dialect → AST checks | Regex (bypassable), DB permissions alone (no LIMIT, no function control) | `sql_guard.guard` |
| Retrieval | BM25 (own) + hashing embeddings (own) + RRF | Reproducible, offline, hybrid | FAISS/pgvector/Qdrant + hosted embeddings (prod path) | `Embedder`, `HybridIndex` |
| API | **FastAPI** + uvicorn | Typed, async, OpenAPI for free | Flask (no typing/validation), gRPC (overkill for this client mix) | — |
| Validation | **pydantic v2** | One schema for API, tools (→ JSON Schema for Claude) and settings | marshmallow | — |
| Config | pydantic-settings | Typed env config, `.env` support | dynaconf | `Settings` |
| Interop | **MCP** (`mcp` 2.x `MCPServer`) | Standard way for any agent/IDE to call our tools | Custom plugin APIs per client | Same `TOOLS` registry |
| Metrics | prometheus-client | Standard, pull-based, Grafana-ready | StatsD | `observability.py` |
| Tracing/logs | Own JSON logger + spans | No vendor lock; OTel-ready | OpenTelemetry SDK, Langfuse, LangSmith (drop-in later) | `observability.py` |
| Registry | Files + optional MLflow mirror | Zero-ops, atomic, auditable | MLflow only (server to run), SageMaker registry (cloud lock-in) | `Registry` |
| Packaging | hatchling, `src/` layout | Standard PEP 621 | Poetry | — |
| Quality | ruff, mypy (pydantic plugin), pytest | Fast, strict, standard | flake8+black+isort (3 tools) | — |
| Container | Multi-stage Docker, non-root, healthcheck | Small attack surface; same image for API, jobs, MCP | — | — |
| Orchestration | docker compose (local), Kubernetes (prod: Deployment + HPA + CronJob) | Same image, two scales | ECS, Cloud Run | `infra/` |
| CI | GitHub Actions: lint, types, tests, **eval gate**, image build; nightly real-model eval | Quality is gated, not hoped for | — | — |

## Deliberately *not* used

* **A vector database** – 21 chunks fit in a NumPy matrix; a DB would add ops for no gain. Interface ready.
* **Prophet** – slower, and on daily retail with promos it is usually beaten by ETS + GBM.
* **Deep forecasting models** – data size (48 series) does not justify them; global GBM is the right tool here.
* **Multi-agent frameworks** – one bounded tool loop solves the problem (see agent-design.md).
* **Fine-tuning (LoRA/PEFT)** – nothing to fine-tune for: the LLM's job is tool choice and explanation, and every fact comes from tools. Fine-tuning would make sense for a domain classifier (e.g. routing at scale on a small open model) – noted on the roadmap.
