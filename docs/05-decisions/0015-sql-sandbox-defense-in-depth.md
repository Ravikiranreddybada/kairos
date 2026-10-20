# ADR-0015: Text-to-SQL sandbox in depth

Status: Accepted · Date: 2026-10-18 · Extends ADR-0012

## Context

The AST guard (`sql_guard.py`) blocked writes, file readers and unknown tables, but (1) functions were checked against a deny-list, so any DuckDB function nobody listed passed; (2) `LIMIT` does not bound work – `SELECT COUNT(*) FROM fact_sales a, fact_sales b, fact_sales c` ran unbounded and held the single warehouse lock, stalling every user; (3) if the guard had a bug, the engine itself could read files.

## Decision

Three walls:
1. **Guard**: functions sqlglot does not recognise (`exp.Anonymous`) must be on an allow-list.
2. **Engine**: the DuckDB connection opens with `enable_external_access=false` and `lock_configuration=true` – no file reads, no ATTACH, no extension loading even for SQL that passes the guard. pandas `register` still works for loads/publish.
3. **Time**: `Warehouse.query(timeout_s=...)` interrupts the statement with `cursor.interrupt()` from a timer; the tool returns a recoverable error (`KAIROS_SQL_TIMEOUT_S`, default 5 s).

## Consequences

+ Tested: unknown UDFs rejected, normal analytics functions allowed, `read_csv` raises `PermissionException` at engine level, a 3-way cross join stops in < 3 s and the connection stays usable.
− New analytics functions that sqlglot does not type need an allow-list entry.

## Alternatives considered

Separate read-only DB file for the agent (better isolation, needs a replication step; the right move with Postgres/Snowflake via a read-only role); regex filters (rejected, ADR-0012).
