# Architecture

## Context (C4 level 1)

```mermaid
flowchart LR
  planner([Planner]) -->|chat, dashboards| K[Kairos]
  agents([Other agents / IDEs]) -->|MCP| K
  ops([Platform engineer]) -->|metrics, logs| K
  K -->|Messages API| claude[(Claude API)]
  K -->|reads| dw[(Sales / inventory / supplier data)]
  K -->|reads| docs[(Policy documents)]
```

## Containers (C4 level 2)

```mermaid
flowchart TB
  subgraph Delivery
    API[REST API<br/>FastAPI]
    MCP[MCP server<br/>stdio / HTTP]
    CLI[CLI]
  end
  subgraph Orchestration
    AG[Copilot<br/>LangGraph state machine]
  end
  subgraph Language
    LLM[LLM client<br/>routing, caching, fallback]
    RAG[Hybrid retriever<br/>BM25 + dense + RRF]
    GR[Guardrails<br/>injection, PII, grounding]
    SC[Semantic cache]
  end
  subgraph Decision science
    FS[Forecast service<br/>read side]
    TP[Training pipeline<br/>write side]
    INV[Inventory policy]
    AN[Anomaly detector]
  end
  subgraph State
    WH[(Warehouse<br/>DuckDB → Postgres/Snowflake)]
    REG[(Model registry<br/>files → S3 + MLflow)]
    MEM[(Session memory<br/>SQLite → Redis/Postgres)]
  end
  API --> AG
  MCP --> TOOLS
  AG --> TOOLS[Tool registry<br/>8 typed tools]
  AG --> LLM & GR & SC
  TOOLS --> FS & INV & AN & RAG
  TOOLS -->|guarded SQL| WH
  FS --> WH & REG
  TP --> WH & REG
  AG --> MEM
```

## Layering rule

Dependencies only point **down**. Enforced by review and by the package
layout (`kairos/__init__.py` documents it).

```
delivery      api · mcp_server · cli
orchestration agent
language      llm · rag
decision      forecasting · inventory · anomaly
data          data
cross-cutting config · observability · bootstrap (composition root)
```

`bootstrap.build()` is the **composition root**: the only place that picks
concrete classes. API, MCP, CLI and tests all call it, so they cannot drift.

## Key architectural decisions (summary)

| Concern | Decision | ADR |
|---|---|---|
| Forecast serving | CQRS split: batch training writes `fact_forecast`; API only reads | [0007](../05-decisions/0007-batch-train-online-serve.md) |
| Uncertainty | Split-conformal intervals on any point model | [0006](../05-decisions/0006-conformal-intervals.md) |
| Features | Horizon-safe lags, direct multi-horizon model | [0005](../05-decisions/0005-horizon-safe-direct-forecasting.md) |
| Censored demand | Mask stockout days in targets, features and metrics | [0004](../05-decisions/0004-censored-demand.md) |
| Agent control | Explicit LangGraph state machine, not free ReAct | [0012](../05-decisions/0012-explicit-agent-graph-read-only-tools.md) |
| CI for LLM | Deterministic FakeLLM gate on every PR, real model nightly | [0010](../05-decisions/0010-offline-eval-gate-fake-llm.md) |
| Retrieval | Hybrid BM25 + dense with RRF | [0011](../05-decisions/0011-hybrid-retrieval.md) |
| Interop | Single tool registry for agent, MCP and API | [0002](../05-decisions/0002-single-tool-registry-mcp.md) |

## Request lifecycle: "Should we reorder SKU002 at S01?"

```mermaid
sequenceDiagram
  participant U as Planner
  participant A as API
  participant G as Copilot graph
  participant L as Claude (strong tier)
  participant T as inventory_policy tool
  participant F as ForecastService
  participant W as Warehouse
  U->>A: POST /v1/agent/chat
  A->>A: auth, rate-limit (weight 5), trace id
  A->>G: ask(question, session)
  G->>G: guard (injection?) → cache (miss) → route (strong: "should")
  G->>L: system + tools + history + question
  L-->>G: tool_use inventory_policy(S01, SKU002)
  G->>T: validate args (pydantic) → execute
  T->>F: inventory_policy(...)
  F->>W: forecast rows + supplier + on-hand
  F-->>T: decision + trade-off + run_id
  T-->>G: compact JSON
  G->>L: tool_result
  L-->>G: final text
  G->>G: verify numeric grounding → finalize (citations) → memory, cache
  G-->>A: answer, tool calls, grounding, usage, cost, trace id
  A-->>U: 200 + x-trace-id
```
