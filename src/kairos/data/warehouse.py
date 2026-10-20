"""DuckDB analytical store.

DuckDB gives us columnar, vectorised SQL in-process with zero ops. The
``Warehouse`` interface is the seam: production swaps it for Postgres /
Snowflake / BigQuery without touching callers (ADR-0003).

Hardening (the engine is reached by LLM-written SQL, see ``agent/sql_guard``):
external access is off and locked, so even a query that slips past the guard
cannot read files, attach databases or load extensions; ``query`` accepts a
timeout that interrupts runaway statements.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pandas as pd

from kairos.data.synthetic import SyntheticDataset

# pandas DataFrames passed to ``cursor.register`` still work with this config.
SANDBOX_CONFIG: dict[str, str | bool | int | float | list[str]] = {
    "enable_external_access": False, "lock_configuration": True}


class QueryTimeout(RuntimeError):
    """A query exceeded its time budget and was interrupted."""


TABLES = ("dim_store", "dim_sku", "dim_supplier", "fact_sales", "fact_inventory")

SCHEMA_DOC = """
dim_store(store_id TEXT PK, region TEXT, size_factor DOUBLE)
dim_sku(sku_id TEXT PK, category TEXT, supplier_id TEXT FK, base_price DOUBLE, unit_cost DOUBLE,
        holding_cost_rate_annual DOUBLE, base_demand DOUBLE, is_intermittent BOOLEAN)
dim_supplier(supplier_id TEXT PK, name TEXT, lead_time_mean_days DOUBLE, lead_time_std_days DOUBLE,
             moq_units INTEGER, on_time_rate DOUBLE)
fact_sales(date DATE, store_id TEXT, sku_id TEXT, units_sold INTEGER, price DOUBLE,
           on_promo BOOLEAN, stockout BOOLEAN)   -- grain: one row per day x store x sku
fact_inventory(store_id TEXT, sku_id TEXT, as_of DATE, on_hand_units INTEGER, on_order_units INTEGER)
""".strip()


class Warehouse:
    def __init__(self, path: Path | str = ":memory:", read_only: bool = False) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(self.path, read_only=read_only, config=SANDBOX_CONFIG)
        self._lock = threading.Lock()  # DuckDB connections are not thread-safe

    @contextmanager
    def cursor(self) -> Iterator[duckdb.DuckDBPyConnection]:
        with self._lock:
            cur = self._con.cursor()
            try:
                yield cur
            finally:
                cur.close()

    def load(self, ds: SyntheticDataset) -> None:
        frames = {
            "dim_store": ds.stores,
            "dim_sku": ds.skus,
            "dim_supplier": ds.suppliers,
            "fact_sales": ds.sales,
            "fact_inventory": ds.inventory,
        }
        with self.cursor() as cur:
            for name, df in frames.items():
                cur.register("_tmp", df)
                cur.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _tmp")
                cur.unregister("_tmp")
            cur.execute("CREATE OR REPLACE VIEW v_sales AS SELECT * FROM fact_sales")

    def query(self, sql: str, params: list[object] | None = None, timeout_s: float | None = None) -> pd.DataFrame:
        with self.cursor() as cur:
            if timeout_s is None:
                return cur.execute(sql, params or []).df()
            timer = threading.Timer(timeout_s, cur.interrupt)
            timer.start()
            try:
                return cur.execute(sql, params or []).df()
            except duckdb.InterruptException as e:
                raise QueryTimeout(f"query exceeded {timeout_s:g}s and was stopped") from e
            finally:
                timer.cancel()

    def sales(self, store_id: str | None = None, sku_id: str | None = None) -> pd.DataFrame:
        where: list[str] = []
        params: list[object] = []
        if store_id:
            where.append("store_id = ?")
            params.append(store_id)
        if sku_id:
            where.append("sku_id = ?")
            params.append(sku_id)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        df = self.query(f"SELECT * FROM fact_sales {clause} ORDER BY store_id, sku_id, date", params)
        df["date"] = pd.to_datetime(df["date"])
        return df

    def table(self, name: str) -> pd.DataFrame:
        if name not in TABLES:
            raise ValueError(f"unknown table {name}")
        return self.query(f"SELECT * FROM {name}")

    def close(self) -> None:
        self._con.close()
