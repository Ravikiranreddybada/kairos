"""Explainable anomaly detection on daily sales.

Approach: robust residual scoring.

    baseline_t = rolling median (29d, centred) x weekday factor
    score_t    = (y_t - baseline_t) / (1.4826 * MAD of residuals)

Why not IsolationForest/autoencoders: planners must be told *why* a point is
flagged ("4.8 robust std above the weekday-adjusted baseline"), and robust
statistics give that for free, with no training and no drift. Known causes
(promotions, festivals, stockouts) are attributed instead of flagged, which
removes the false positives that make users ignore alerting systems.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from kairos.data.synthetic import festival_flag
from kairos.forecasting.features import KEYS


@dataclass(frozen=True)
class DetectorConfig:
    window: int = 29
    threshold: float = 4.0
    min_baseline: float = 2.0  # below this, series is too sparse for daily anomalies


def score(sales: pd.DataFrame, cfg: DetectorConfig | None = None) -> pd.DataFrame:
    cfg = cfg or DetectorConfig()
    parts = []
    for _, g in sales.sort_values("date").groupby(KEYS, sort=False):
        g = g.copy()
        y = g["units_sold"].astype(float)
        level = y.rolling(cfg.window, center=True, min_periods=cfg.window // 2).median()
        dow = g["date"].dt.dayofweek
        ratio = (y / level.replace(0, np.nan)).groupby(dow).transform("median").fillna(1.0)
        baseline = level * ratio
        resid = y - baseline
        mad = float(np.nanmedian(np.abs(resid - np.nanmedian(resid))))
        robust_sd = max(1.4826 * mad, 1.0)
        g["baseline"] = baseline
        g["score"] = resid / robust_sd
        parts.append(g)
    out = pd.concat(parts, ignore_index=True)
    out["festival"] = festival_flag(pd.DatetimeIndex(out["date"])) > 0.2
    return out


def detect(sales: pd.DataFrame, cfg: DetectorConfig | None = None) -> pd.DataFrame:
    cfg = cfg or DetectorConfig()
    s = score(sales, cfg)
    cand = s[(s["score"].abs() >= cfg.threshold) & (s["baseline"] >= cfg.min_baseline)].copy()
    cand["explained_by"] = np.select(
        [cand["stockout"], cand["on_promo"], cand["festival"]],
        ["stockout", "promotion", "festival"],
        default="",
    )
    cand["kind"] = np.where(cand["score"] > 0, "spike", "drop")
    cand["explanation"] = cand.apply(
        lambda r: (
            f"{r.units_sold:.0f} units vs expected {r.baseline:.1f} "
            f"({r.score:+.1f} robust std)"
            + (f"; likely due to {r.explained_by}" if r.explained_by else "; no known cause")
        ),
        axis=1,
    )
    cols = ["date", "store_id", "sku_id", "units_sold", "baseline", "score", "kind", "explained_by", "explanation"]
    return cand[cols].sort_values("score", key=np.abs, ascending=False).reset_index(drop=True)


def evaluate(flags: pd.DataFrame, truth: pd.DataFrame) -> dict[str, float]:
    """Precision/recall of *unexplained* flags against injected ground truth."""
    f = flags[flags["explained_by"] == ""]
    key = ["date", "store_id", "sku_id"]
    f_keys = set(map(tuple, f[key].astype(str).to_numpy()))
    t_keys = set(map(tuple, truth[key].astype(str).to_numpy()))
    tp = len(f_keys & t_keys)
    precision = tp / len(f_keys) if f_keys else 0.0
    recall = tp / len(t_keys) if t_keys else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "flags": float(len(f_keys)), "truth": float(len(t_keys))}
