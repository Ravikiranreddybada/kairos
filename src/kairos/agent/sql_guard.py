"""Text-to-SQL safety: parse, don't regex.

LLM-written SQL runs against business data, so it is validated on the AST
(sqlglot), not by string matching (which ``/**/DROP`` or unicode tricks
defeat). Policy:

* exactly one statement, and it must be a SELECT (CTEs allowed)
* only allow-listed tables/views
* no table functions / file readers (``read_csv``, ``read_parquet``, ``glob``...)
* functions sqlglot does not recognise (``exp.Anonymous``) must be on an
  allow-list: a deny-list can never name every DuckDB extension function
* a LIMIT is always enforced (injected or clamped)

Defense in depth: the guard is the first wall, not the only one. The
warehouse engine itself has external access disabled (no files, no
extensions) and every LLM query runs under a timeout that interrupts it
(``Warehouse.query(timeout_s=...)``), which stops cross-join blow-ups that
a LIMIT cannot.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = frozenset(
    {"dim_store", "dim_sku", "dim_supplier", "fact_sales", "fact_inventory", "fact_forecast",
     "fact_forecast_hierarchy", "v_sales"}
)
BLOCKED_FUNCS = frozenset(
    {"read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto", "glob", "read_text",
     "read_blob", "query", "query_table", "sniff_csv", "getenv", "current_setting"}
)
# Unrecognised-by-sqlglot functions that are safe and common in planning analytics.
ALLOWED_ANON_FUNCS = frozenset(
    {"dayofweek", "dayofyear", "dayname", "monthname", "isodow", "week", "weekofyear", "yearweek",
     "date_part", "datepart", "quantile", "quantile_disc", "mode", "arg_max", "arg_min", "list",
     "greatest", "least", "round_even", "log10", "log2", "ln", "nullif", "ifnull", "regr_slope", "corr",
     "covar_pop", "covar_samp", "stddev_pop", "stddev_samp", "var_pop", "var_samp", "kurtosis", "skewness"}
)
MAX_ROWS = 200


class UnsafeSQL(ValueError):
    pass


@dataclass(frozen=True)
class GuardedSQL:
    sql: str
    tables: frozenset[str]


def guard(sql: str, max_rows: int = MAX_ROWS) -> GuardedSQL:
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQL(f"could not parse SQL: {e.errors[0]['description'] if e.errors else e}") from e
    if len(statements) != 1:
        raise UnsafeSQL("exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, exp.Select | exp.Union | exp.Intersect | exp.Except):
        raise UnsafeSQL(f"only SELECT queries are allowed (got {tree.key.upper()})")
    for bad in (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Pragma):
        if tree.find(bad) is not None:
            raise UnsafeSQL(f"{bad.__name__.upper()} is not allowed")

    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    tables = set()
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if not name:
            raise UnsafeSQL("table functions are not allowed")
        if name in cte_names:
            continue
        if t.args.get("db") or t.args.get("catalog"):
            raise UnsafeSQL("schema-qualified tables are not allowed")
        if name not in ALLOWED_TABLES:
            raise UnsafeSQL(f"table '{name}' is not allowed")
        tables.add(name)
    for f in tree.find_all(exp.Func):
        fname = (f.sql_name() if not isinstance(f, exp.Anonymous) else f.name).lower()
        if fname in BLOCKED_FUNCS:
            raise UnsafeSQL(f"function '{fname}' is not allowed")
        if isinstance(f, exp.Anonymous) and fname not in ALLOWED_ANON_FUNCS:
            raise UnsafeSQL(f"function '{fname}' is not on the allow-list")
    for t in tree.find_all(exp.Table):
        if isinstance(t.this, exp.Func):
            raise UnsafeSQL("table functions are not allowed")

    limit = tree.args.get("limit")
    if limit is None:
        tree = tree.limit(max_rows)
    else:
        try:
            n = int(limit.expression.name)
        except (AttributeError, ValueError):
            n = max_rows + 1
        if n > max_rows:
            tree = tree.limit(max_rows)
    return GuardedSQL(tree.sql(dialect="duckdb"), frozenset(tables))
