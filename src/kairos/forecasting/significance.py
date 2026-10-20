"""Is the challenger *really* better? Diebold-Mariano test on backtest errors.

A 2% WAPE gain over a few backtest folds can be noise. Promoting on noise
churns forecasts (and planner trust) for nothing. The Diebold-Mariano test
(1995) asks whether the mean loss differential between two forecasts is
different from zero, with a HAC (Newey-West) variance so autocorrelated daily
errors do not inflate confidence. The Harvey-Leybourne-Newbold (1997)
correction and Student-t reference fix its over-rejection in small samples.

Panel data -> one series: for each date, sum the absolute errors over all
store x SKU series (volume-weighted, like WAPE), then test the daily
differential ``d_t = loss_challenger_t - loss_champion_t``. One-sided:
small p-value = challenger has lower loss.

Uses ``statsmodels.tsa.stattools.diebold_mariano_test``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import diebold_mariano_test

_KEY = ["date", "store_id", "sku_id"]


def _daily_abs_loss(oof: pd.DataFrame) -> pd.Series:
    d = oof[~oof["stockout"].astype(bool)]
    return (d["y"] - d["yhat"]).abs().groupby(d["date"]).sum()


def compare_forecasts(challenger: pd.DataFrame, champion: pd.DataFrame) -> dict[str, Any]:
    """One-sided DM test that ``challenger`` has lower absolute error than ``champion``.

    Both frames: date, store_id, sku_id, y, yhat, stockout (same rows, e.g. the
    same backtest folds). Returns statistic, one-sided p-value, n days, mean diff.
    """
    keys = challenger[_KEY].merge(champion[_KEY], on=_KEY)  # compare only rows both models scored
    a = _daily_abs_loss(challenger.merge(keys, on=_KEY))
    b = _daily_abs_loss(champion.merge(keys, on=_KEY))
    a, b = a.align(b, join="inner")
    n = len(a)
    diff = a.to_numpy() - b.to_numpy()
    if n < 3 or np.allclose(diff, 0):
        return {"statistic": 0.0, "p_value": 1.0, "n": n, "mean_loss_diff": float(diff.mean()) if n else 0.0}
    # y = 0 with criterion 'mad' turns the "forecasts" into the loss series themselves.
    res = diebold_mariano_test(np.zeros(n), a.to_numpy(), b.to_numpy(), criterion="mad", harvey_adj=True)
    stat, p_two = float(res.statistic), float(res.pvalue)
    p_one = p_two / 2 if stat < 0 else 1 - p_two / 2
    return {"statistic": round(stat, 4), "p_value": round(p_one, 6), "n": n,
            "mean_loss_diff": round(float(diff.mean()), 4)}
