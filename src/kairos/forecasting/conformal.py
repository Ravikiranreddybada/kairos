"""Split-conformal prediction intervals on top of any point forecaster.

Why conformal (ADR-0006): it is model-agnostic, needs no distributional
assumption, and gives a finite-sample coverage guarantee under
exchangeability. Two refinements make it work for retail:

1. **Scale normalisation** – residuals are divided by each series' MASE
   scale, so one calibration set serves SKUs selling 1/day and 100/day.
2. **Horizon buckets** – error grows with lead time; we calibrate a separate
   quantile per week of horizon (h 1-7, 8-14, ...).

Honest evaluation: ``evaluate_coverage`` calibrates on earlier folds and
measures coverage on the last fold, which the calibrator never saw.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from kairos.forecasting.features import KEYS
from kairos.forecasting.metrics import mase_scale


def series_scales(sales: pd.DataFrame, m: int = 7) -> pd.Series:
    clean = sales[~sales["stockout"]]
    return clean.sort_values("date").groupby(KEYS)["units_sold"].apply(lambda s: mase_scale(s.to_numpy(float), m))


def _bucket(h: pd.Series | np.ndarray) -> np.ndarray:
    return ((np.asarray(h) - 1) // 7).astype(int)


@dataclass
class ConformalCalibrator:
    alpha: float = 0.2
    quantiles: dict[int, float] = field(default_factory=dict)
    scales: dict[tuple[str, str], float] = field(default_factory=dict)

    def fit(self, oof: pd.DataFrame, scales: pd.Series) -> ConformalCalibrator:
        self.scales = {k: float(v) for k, v in scales.items()}
        d = oof[~oof["stockout"]].copy()
        s = np.array([self.scales.get(k, 1.0) for k in zip(d.store_id, d.sku_id, strict=True)])
        d["score"] = np.abs(d["y"] - d["yhat"]) / s
        d["bucket"] = _bucket(d["h"])
        for b, g in d.groupby("bucket"):
            n = len(g)
            # Finite-sample correction: ceil((n+1)(1-alpha))/n quantile.
            level = min(1.0, np.ceil((n + 1) * (1 - self.alpha)) / n)
            self.quantiles[int(b)] = float(np.quantile(g["score"], level, method="higher"))
        return self

    def apply(self, pred: pd.DataFrame, h: pd.Series | np.ndarray) -> pd.DataFrame:
        if not self.quantiles:
            raise RuntimeError("calibrator not fitted")
        max_b = max(self.quantiles)
        b = np.minimum(_bucket(h), max_b)
        q = np.array([self.quantiles[int(x)] for x in b])
        s = np.array([self.scales.get(k, 1.0) for k in zip(pred.store_id, pred.sku_id, strict=True)])
        out = pred.copy()
        out["lo"] = np.clip(pred["yhat"].to_numpy() - q * s, 0, None)
        out["hi"] = pred["yhat"].to_numpy() + q * s
        return out


def evaluate_coverage(oof: pd.DataFrame, scales: pd.Series, alpha: float) -> dict[str, float]:
    last = oof["fold"].max()
    cal = ConformalCalibrator(alpha=alpha).fit(oof[oof["fold"] < last], scales)
    test = oof[(oof["fold"] == last) & ~oof["stockout"]]
    scored = cal.apply(test, test["h"])
    cov = float(np.mean((scored["y"] >= scored["lo"]) & (scored["y"] <= scored["hi"])))
    return {"nominal": 1 - alpha, "empirical": cov, "mean_width": float((scored["hi"] - scored["lo"]).mean())}
