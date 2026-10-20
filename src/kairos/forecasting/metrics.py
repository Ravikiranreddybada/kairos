"""Forecast accuracy metrics.

Choice of headline metric matters more than most model choices:

* **WAPE** (sum|e| / sum|y|) is the business metric: volume-weighted, robust
  to zeros, and maps directly to "units we got wrong".
* **MASE** scales by an in-sample seasonal-naive error, so it is comparable
  across SKUs of any volume and tells us if we beat the trivial baseline (<1).
* **Bias** catches systematic over/under-forecasting, which drives excess
  stock or lost sales even when WAPE looks fine.
* MAPE is deliberately absent: undefined at zero, explodes on slow movers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def wape(y: np.ndarray, yhat: np.ndarray) -> float:
    denom = np.abs(y).sum()
    return float(np.abs(y - yhat).sum() / denom) if denom > 0 else float("nan")


def bias(y: np.ndarray, yhat: np.ndarray) -> float:
    """Positive = over-forecast, as a share of actual volume."""
    denom = np.abs(y).sum()
    return float((yhat - y).sum() / denom) if denom > 0 else float("nan")


def smape(y: np.ndarray, yhat: np.ndarray) -> float:
    denom = np.abs(y) + np.abs(yhat)
    mask = denom > 0
    return float(np.mean(2 * np.abs(y - yhat)[mask] / denom[mask])) if mask.any() else 0.0


def mase_scale(history: np.ndarray, m: int = 7) -> float:
    """Mean absolute seasonal-naive error on the training history."""
    if len(history) <= m:
        return float(np.mean(np.abs(np.diff(history)))) if len(history) > 1 else 1.0
    scale = float(np.mean(np.abs(history[m:] - history[:-m])))
    return scale if scale > 0 else 1.0


def pinball(y: np.ndarray, q_pred: np.ndarray, q: float) -> float:
    diff = y - q_pred
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    return float(np.mean((y >= lo) & (y <= hi)))


def summarize(df: pd.DataFrame, scales: pd.Series | None = None) -> dict[str, float]:
    """Metrics over a frame with ``y``/``yhat`` (and optionally ``lo``/``hi``).

    Rows flagged ``stockout`` are excluded: on those days we observed sales,
    not demand, so scoring against them rewards under-forecasting.
    """
    d = df[~df["stockout"]] if "stockout" in df else df
    y, yhat = d["y"].to_numpy(float), d["yhat"].to_numpy(float)
    out = {"wape": wape(y, yhat), "bias": bias(y, yhat), "smape": smape(y, yhat), "n": float(len(d))}
    if scales is not None:
        key = list(zip(d.store_id, d.sku_id, strict=True))
        s = np.array([scales.get(k, 1.0) for k in key])
        out["mase"] = float(np.mean(np.abs(y - yhat) / s))
    if {"lo", "hi"} <= set(d.columns):
        out["coverage"] = coverage(y, d["lo"].to_numpy(), d["hi"].to_numpy())
        out["interval_width"] = float(np.mean(d["hi"] - d["lo"]))
    return out
