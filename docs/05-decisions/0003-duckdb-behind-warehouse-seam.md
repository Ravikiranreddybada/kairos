# ADR-0003: DuckDB behind a Warehouse seam

Status: Accepted · Date: 2026-10-18

## Context

We need fast analytical SQL for training, serving and the text-to-SQL tool, and the project must run on a laptop and in CI with no services.

## Decision

Use DuckDB (in-process, columnar). All access goes through `data/warehouse.py::Warehouse` (`query`, `sales`, `table`, `load`, `cursor`). A lock serialises access because DuckDB connections are not thread-safe.

## Consequences

+ Zero ops; `kairos seed` creates the database; CI needs nothing.
+ The text-to-SQL tool runs real SQL against a real engine.
− Single writer; not a multi-replica serving store. Production swaps the implementation for Postgres (serving) / Snowflake (analytics) – see scaling.md.

## Alternatives considered

SQLite (row store; slow aggregates); Postgres in docker-compose for dev (heavier; nothing gained for 35k rows).
