# ADR-0002: One tool registry for agent, MCP and API

Status: Accepted · Date: 2026-10-18

## Context

The same capabilities (forecast, policy, what-if, anomalies, SQL, docs) are needed by the copilot, by other agents/IDEs over MCP, and partly by the REST API. Separate implementations drift: a guard added to one channel is missing in another.

## Decision

`agent/tools.py::TOOLS` is the single registry: pydantic input model + function. It generates Claude tool definitions (JSON Schema, sorted for cache stability) and backs every MCP tool via `execute()`. The REST API calls the same services.

## Consequences

+ Validation, SQL guard, metrics and error mapping are identical everywhere (tested: MCP DROP TABLE is rejected the same way).
+ Adding a capability is one function + one model.
− MCP tool signatures are written out explicitly (MCP derives schemas from Python signatures), so a parameter change touches two places; covered by `test_mcp_server_exposes_same_tools`.

## Alternatives considered

Generate MCP tools dynamically from pydantic models (possible, but hides the signature from MCP's schema inference and readers); separate MCP implementation (rejected: drift).
