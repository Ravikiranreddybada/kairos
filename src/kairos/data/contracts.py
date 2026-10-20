"""Data contracts: fail loudly *before* bad data reaches a model.

Each check returns a ``CheckResult`` instead of raising, so the pipeline can
decide policy (block on ``error``, warn on ``warn``). Results are persisted
next to the model so every forecast is traceable to the data quality of its
training set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

Severity = Literal["ok", "warn", "error"]

SALES_SCHEMA: dict[str, str] = {
    "date": "datetime64[ns]",
    "store_id": "string",
    "sku_id": "string",
    "units_sold": "int",
    "price": "float",
    "on_promo": "bool",
    "stockout": "bool",
}


@dataclass
class CheckResult:
    name: str
    severity: Severity
    detail: str
    failing_rows: int = 0


@dataclass
class QualityReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.severity != "error" for c in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "checks": [c.__dict__ for c in self.checks],
        }


def _dtype_family(series: pd.Series) -> str:
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime64[ns]"
    if pd.api.types.is_bool_dtype(series):
        return "bool"
    if pd.api.types.is_integer_dtype(series):
        return "int"
    if pd.api.types.is_float_dtype(series):
        return "float"
    if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
        return "string"
    return str(series.dtype)


def validate_sales(df: pd.DataFrame, max_gap_days: int = 3) -> QualityReport:
    report = QualityReport()

    missing = [c for c in SALES_SCHEMA if c not in df.columns]
    if missing:
        report.checks.append(CheckResult("schema.columns", "error", f"missing columns: {missing}"))
        return report
    wrong = {
        c: _dtype_family(df[c]) for c, want in SALES_SCHEMA.items() if _dtype_family(df[c]) != want
    }
    report.checks.append(
        CheckResult("schema.dtypes", "error" if wrong else "ok", f"unexpected dtypes: {wrong}" if wrong else "ok")
    )

    nulls = int(df[list(SALES_SCHEMA)].isna().sum().sum())
    report.checks.append(CheckResult("nulls", "error" if nulls else "ok", f"{nulls} null cells", nulls))

    neg = int((df.units_sold < 0).sum())
    report.checks.append(CheckResult("units.non_negative", "error" if neg else "ok", f"{neg} negative rows", neg))

    bad_price = int((df.price <= 0).sum())
    report.checks.append(CheckResult("price.positive", "error" if bad_price else "ok", f"{bad_price} rows", bad_price))

    dupes = int(df.duplicated(["date", "store_id", "sku_id"]).sum())
    report.checks.append(CheckResult("grain.unique", "error" if dupes else "ok", f"{dupes} duplicate keys", dupes))

    # Gaps: missing calendar days per series silently break lag features.
    gaps = (
        df.sort_values("date")
        .groupby(["store_id", "sku_id"])["date"]
        .apply(lambda s: int(s.diff().dt.days.max() or 1))
    )
    worst = int(gaps.max()) if len(gaps) else 0
    sev: Severity = "error" if worst > max_gap_days else ("warn" if worst > 1 else "ok")
    report.checks.append(CheckResult("calendar.gaps", sev, f"max gap {worst} days"))

    stockout_share = float(df.stockout.mean())
    report.checks.append(
        CheckResult(
            "stockout.share",
            "warn" if stockout_share > 0.05 else "ok",
            f"{stockout_share:.2%} of rows censored by stockouts",
        )
    )

    # Freshness relative to the newest row (a stale feed is a silent killer).
    span = (df.date.max() - df.date.min()).days
    report.checks.append(CheckResult("history.length", "warn" if span < 365 else "ok", f"{span} days of history"))
    return report
