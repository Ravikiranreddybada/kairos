"""Rolling-origin backtesting (time-series cross-validation).

Random K-fold leaks the future into training. We instead slide the cutoff
backwards in steps of ``horizon``; each fold trains on data up to its cutoff
and is scored on the next ``horizon`` days.

    |-------- train --------|== test ==|
    |----- train -----|== test ==|
    |-- train --|== test ==|

The out-of-fold residuals feed conformal calibration, so intervals are
calibrated on errors the model actually makes out of sample.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from kairos.forecasting.features import KEYS
from kairos.forecasting.models import Forecaster
from kairos.observability import get_logger, span

log = get_logger(__name__)


@dataclass
class Fold:
    index: int
    cutoff: pd.Timestamp
    test_end: pd.Timestamp


def make_folds(last_date: pd.Timestamp, horizon: int, n_folds: int) -> list[Fold]:
    folds = []
    for k in range(n_folds, 0, -1):
        cutoff = last_date - pd.Timedelta(days=horizon * k)
        folds.append(Fold(index=n_folds - k, cutoff=cutoff, test_end=cutoff + pd.Timedelta(days=horizon)))
    return folds


def backtest(
    model: Forecaster,
    sales: pd.DataFrame,
    skus: pd.DataFrame,
    horizon: int,
    n_folds: int,
) -> pd.DataFrame:
    """Return out-of-fold predictions joined to actuals.

    Columns: fold, date, store_id, sku_id, h (1..H), y, yhat, stockout.
    """
    folds = make_folds(sales["date"].max(), horizon, n_folds)
    parts = []
    for f in folds:
        with span("backtest.fold", model=model.name, fold=f.index, cutoff=str(f.cutoff.date())):
            train = sales[sales["date"] <= f.cutoff]
            test = sales[(sales["date"] > f.cutoff) & (sales["date"] <= f.test_end)]
            future = test[["date", *KEYS, "price", "on_promo"]]
            model.fit(train, skus)
            pred = model.predict(train, future)
            merged = test[["date", *KEYS, "units_sold", "stockout"]].merge(pred, on=["date", *KEYS], how="left")
            merged = merged.rename(columns={"units_sold": "y"})
            merged["h"] = (merged["date"] - f.cutoff).dt.days
            merged["fold"] = f.index
            parts.append(merged)
    out = pd.concat(parts, ignore_index=True)
    missing = int(out["yhat"].isna().sum())
    if missing:
        log.warning("backtest produced missing predictions", fields={"model": model.name, "missing": missing})
        out["yhat"] = out["yhat"].fillna(0.0)
    return out
