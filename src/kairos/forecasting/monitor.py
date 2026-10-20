"""Model health: is the champion still looking at the world it was trained on?

Backtests say how good a model *was*. Between retrains the world moves. Two
cheap, label-free signals catch most of it:

* **Population Stability Index (PSI)** of each series' recent demand against
  its own reference window. The textbook cut-offs (0.1 / 0.25) assume large
  samples; 28 daily points carry ~0.3 PSI of pure noise. So each series gets
  its own **noise floor**: the 95th percentile of PSI between random 28-day
  windows *inside* the reference period and the reference itself. Drift =
  PSI above both 0.25 and that floor.
* **Level shift**: recent mean demand vs the published forecast mean. A model
  that forecasts 40 units/day for a series now selling 25 is stale even when
  its backtest WAPE was excellent. Counted only when it is both material
  (> 25%) and statistically clear (> 2 standard errors), so slow movers
  selling 0.2 vs 0.7 units/day do not raise alarms.

Stockout days are censored demand and are excluded from both (ADR-0004).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from kairos.forecasting.features import KEYS

PSI_MODERATE, PSI_MAJOR = 0.10, 0.25  # conventional cut-offs; see noise floor below


def psi(reference: np.ndarray, recent: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index with reference-quantile bins (robust to zero-heavy demand)."""
    ref, cur = np.asarray(reference, float), np.asarray(recent, float)
    if len(ref) < 20 or len(cur) < 7:
        return 0.0
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:  # near-constant reference: compare zero/non-zero mass only
        edges = np.array([-np.inf, 0.5, np.inf])
    edges[0], edges[-1] = -np.inf, np.inf
    p = np.histogram(ref, edges)[0] / len(ref)
    q = np.histogram(cur, edges)[0] / len(cur)
    p, q = np.clip(p, 1e-4, None), np.clip(q, 1e-4, None)
    return float(np.sum((q - p) * np.log(q / p)))


def psi_noise_floor(reference: np.ndarray, window: int, rng: np.random.Generator, draws: int = 40) -> float:
    """95th percentile of PSI between random contiguous windows of the reference and the reference."""
    ref = np.asarray(reference, float)
    if len(ref) < 2 * window:
        return PSI_MAJOR
    starts = rng.integers(0, len(ref) - window, size=draws)
    return float(np.percentile([psi(ref, ref[s : s + window]) for s in starts], 95))


@dataclass(frozen=True)
class HealthConfig:
    recent_days: int = 28
    reference_days: int = 182
    level_shift_threshold: float = 0.25  # |recent / forecast - 1|
    retrain_share: float = 0.2  # retrain when this share of series drift
    seed: int = 0


def assess(sales: pd.DataFrame, forecast: pd.DataFrame, manifest: dict[str, Any],
           cfg: HealthConfig | None = None, top_k: int = 5) -> dict[str, Any]:
    cfg = cfg or HealthConfig()
    end = sales["date"].max()
    clean = sales[~sales["stockout"].astype(bool)]
    recent_cut = end - pd.Timedelta(days=cfg.recent_days)
    ref_cut = recent_cut - pd.Timedelta(days=cfg.reference_days)
    fc_mean = forecast.groupby(KEYS)["yhat"].mean()

    rng = np.random.default_rng(cfg.seed)
    rows = []
    for key, g in clean.groupby(KEYS):
        ref = g.loc[(g["date"] > ref_cut) & (g["date"] <= recent_cut), "units_sold"].to_numpy(float)
        cur = g.loc[g["date"] > recent_cut, "units_sold"].to_numpy(float)
        value = psi(ref, cur)
        floor = psi_noise_floor(ref, max(len(cur), 7), rng)
        fm = float(fc_mean.get(key, np.nan))
        rm = float(cur.mean()) if len(cur) else np.nan
        shift = rm / fm - 1 if fm > 0 and np.isfinite(rm) else 0.0
        se = float(cur.std(ddof=1) / np.sqrt(len(cur))) if len(cur) > 1 else np.inf
        level_shift = abs(shift) > cfg.level_shift_threshold and abs(rm - fm) > 2 * se
        distribution = "major" if value > max(PSI_MAJOR, floor) else \
            "moderate" if value > max(PSI_MODERATE, floor) else "stable"
        rows.append({"store_id": key[0], "sku_id": key[1], "psi": round(value, 3),
                     "psi_noise_floor": round(floor, 3), "distribution_drift": distribution,
                     "recent_mean": round(rm, 2) if np.isfinite(rm) else None,
                     "forecast_mean": round(fm, 2) if np.isfinite(fm) else None,
                     "level_shift_pct": round(100 * shift, 1), "level_shift": bool(level_shift),
                     "drifting": bool(distribution == "major" or level_shift)})
    df = pd.DataFrame(rows)
    drifting = df[df["drifting"]]
    share = len(drifting) / len(df) if len(df) else 0.0
    # Only a level shift moves reorder decisions; a changed shape with the level still tracked is "watch".
    shifted = int(df["level_shift"].sum()) if len(df) else 0
    shifted_share = shifted / len(df) if len(df) else 0.0

    created = manifest.get("created_at")
    age_days = None
    if created:
        age_days = round((datetime.now(UTC) - datetime.fromisoformat(created)).total_seconds() / 86400, 1)
    status = "retrain_recommended" if shifted_share >= cfg.retrain_share else "watch" if len(drifting) else "healthy"
    worst = df.assign(rank=df["drifting"].astype(int) * 10 + df["psi"] - df["psi_noise_floor"]
                      + df["level_shift"].astype(int) * df["level_shift_pct"].abs() / 100
                      ).sort_values("rank", ascending=False)
    metrics = manifest.get("metrics", {})
    return {
        "status": status,
        "series_checked": len(df),
        "series_drifting": len(drifting),
        "drifting_share": round(share, 3),
        "series_level_shifted": shifted,
        "champion_age_days": age_days,
        "backtest_wape": metrics.get("wape"),
        "backtest_coverage": metrics.get("coverage_empirical"),
        "recent_window_days": cfg.recent_days,
        "worst": worst.drop(columns="rank").head(top_k).to_dict(orient="records"),
        "run_id": manifest.get("run_id"),
    }
