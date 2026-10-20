"""Leak-safe feature engineering for the global gradient-boosting model.

Key idea – **horizon-safe lags** (ADR-0005): every lag/rolling feature is
shifted by at least ``horizon`` days. One *direct* model can then predict all
H days without recursion, so errors do not compound and train-time features
are exactly what is available at inference time. Leakage is impossible by
construction, and ``tests/unit/test_features.py`` asserts it.

Censored demand: stockout days are masked to NaN *before* computing lags so
"we had nothing to sell" is never learned as "nobody wanted it".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from kairos.data.synthetic import festival_flag

KEYS = ["store_id", "sku_id"]
CATEGORICALS = ["store_id", "sku_id", "category"]


def lag_set(horizon: int) -> list[int]:
    base = [horizon, horizon + 7, horizon + 14, 364]
    return sorted({lag for lag in base if lag >= horizon})


def build_frame(
    history: pd.DataFrame,
    future: pd.DataFrame | None,
    skus: pd.DataFrame,
    horizon: int,
) -> pd.DataFrame:
    """Return history (+ optional future rows) with features attached.

    ``future`` rows carry known-in-advance covariates (price plan, promo plan)
    and ``units_sold = NaN``.
    """
    frame = history.copy()
    frame["is_future"] = False
    if future is not None and len(future):
        fut = future.copy()
        fut["units_sold"] = np.nan
        fut["stockout"] = False
        fut["is_future"] = True
        frame = pd.concat([frame, fut], ignore_index=True)

    frame = frame.sort_values([*KEYS, "date"]).reset_index(drop=True)
    # Only master data a real retailer has. Intermittency is learned from roll_zero_share_28,
    # never from a label (the generator's is_intermittent flag would be a leak).
    frame = frame.merge(skus[["sku_id", "category"]], on="sku_id", how="left")

    demand = frame["units_sold"].astype(float).where(~frame["stockout"].astype(bool))
    g = demand.groupby([frame.store_id, frame.sku_id], sort=False)

    for lag in lag_set(horizon):
        frame[f"lag_{lag}"] = g.shift(lag)
    shifted = g.shift(horizon)
    gs = shifted.groupby([frame.store_id, frame.sku_id], sort=False)
    for w in (7, 28, 91):
        frame[f"roll_mean_{w}"] = gs.transform(lambda s, w=w: s.rolling(w, min_periods=max(2, w // 4)).mean())
    frame["roll_std_28"] = gs.transform(lambda s: s.rolling(28, min_periods=7).std())
    frame["roll_zero_share_28"] = gs.transform(
        lambda s: (s == 0).astype(float).rolling(28, min_periods=7).mean()
    )
    # Same-weekday mean over the last 8 weeks (strong signal for retail).
    for k in range(8):
        frame[f"_dow_lag_{k}"] = g.shift(horizon + (7 - horizon % 7) % 7 + 7 * k)
    dow_cols = [f"_dow_lag_{k}" for k in range(8)]
    frame["dow_mean_8w"] = frame[dow_cols].mean(axis=1)
    frame = frame.drop(columns=dow_cols)

    d = frame["date"]
    frame["dow"] = d.dt.dayofweek
    frame["dom"] = d.dt.day
    frame["month"] = d.dt.month
    frame["doy_sin"] = np.sin(2 * np.pi * d.dt.dayofyear / 365.25)
    frame["doy_cos"] = np.cos(2 * np.pi * d.dt.dayofyear / 365.25)
    frame["festival"] = festival_flag(pd.DatetimeIndex(d))
    frame["on_promo"] = frame["on_promo"].astype(int)
    frame["promo_ended_3d"] = (
        frame.groupby(KEYS, sort=False)["on_promo"].transform(lambda s: s.shift(1).rolling(3, min_periods=1).max())
        .fillna(0)
        .astype(int)
        * (1 - frame["on_promo"])
    )
    frame["price_ratio"] = frame["price"] / frame.groupby(KEYS, sort=False)["price"].transform(
        lambda s: s.shift(horizon).rolling(91, min_periods=7).median()
    )
    for c in CATEGORICALS:
        frame[c] = frame[c].astype("category")
    return frame


def feature_columns(horizon: int) -> list[str]:
    return [
        *CATEGORICALS,
        *[f"lag_{lag}" for lag in lag_set(horizon)],
        "roll_mean_7", "roll_mean_28", "roll_mean_91", "roll_std_28", "roll_zero_share_28",
        "dow_mean_8w", "dow", "dom", "month", "doy_sin", "doy_cos", "festival",
        "on_promo", "promo_ended_3d", "price_ratio",
    ]


def future_frame(history: pd.DataFrame, horizon: int, promo_plan: pd.DataFrame | None = None) -> pd.DataFrame:
    """Future covariates: last observed price, no promo unless a plan says so."""
    last = history.sort_values("date").groupby(KEYS).tail(1)
    start = history["date"].max() + pd.Timedelta(days=1)
    dates = pd.date_range(start, periods=horizon, freq="D")
    rows = last[[*KEYS, "price"]].merge(pd.DataFrame({"date": dates}), how="cross")
    rows["on_promo"] = False
    if promo_plan is not None and len(promo_plan):
        plan = promo_plan.assign(_p=True)[[*KEYS, "date", "_p"]]
        rows = rows.merge(plan, on=[*KEYS, "date"], how="left")
        rows["on_promo"] = rows["_p"].fillna(False).astype(bool)
        rows.loc[rows.on_promo, "price"] *= 0.85
        rows = rows.drop(columns="_p")
    return rows[["date", *KEYS, "price", "on_promo"]]
