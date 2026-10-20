# ADR-0016: Per-session isolation of preferences and cache

Status: Accepted · Date: 2026-10-18 · Supersedes the node order in ADR-0012

## Context

Planner preferences ("our target service level is 99%") were applied by writing `ctx.default_service_level` on the shared `ToolContext`. Every later request from every planner then used 99% – a cross-tenant leak and a race under concurrent requests. The semantic cache ran before preferences were loaded, so a 99% answer was also served to a 95% planner. `/chat/stream` skipped memory and cache entirely, so streamed turns were forgotten.

## Decision

* Preferences live in graph state. Tools run on `dataclasses.replace(ctx, ...)` per request; the shared context is never mutated.
* Graph order is guard → route (load prefs) → cache → llm ⇄ tools → verify → finalize. Cache entries are partitioned by a scope (sorted prefs JSON) and require an exact match of ids, numbers and dates in the question (entity guard), so "reorder SKU002" never answers "reorder SKU003" even with a looser embedder.
* `ask` and `stream` share one `_finish` for memory, cache and audit log.

## Consequences

+ Tested: planner B gets 95% after planner A sets 99%; streamed turns appear in history; cache never crosses entities or scopes.
− Cache hit rate drops slightly (partitioned). Correctness beats hit rate.
