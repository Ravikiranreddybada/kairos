"""Candidate forecasters behind one interface.

Every model is a ``Forecaster``: ``fit(history, skus)`` then
``predict(history, future) -> [date, store_id, sku_id, yhat]``.

* ``SeasonalNaive``   – the bar every model must clear (MASE < 1).
* ``ETSLocal``        – damped-trend Holt-Winters per series (statistics baseline,
                        explains trend/seasonality to stakeholders).
* ``CrostonTSB``      – for intermittent demand where ETS/GBM over-forecast zeros.
* ``LightGBMGlobal``  – one Tweedie GBM across all series; learns cross-series
                        patterns (promo, festival, price) and supports what-if.

Local models are refit per series at predict time (they are cheap and that is
how they are used in practice); the global model is fit once.
"""

from __future__ import annotations

import warnings
from typing import Protocol

import lightgbm as lgb
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from kairos.forecasting.features import KEYS, build_frame, feature_columns

OUT_COLS = ["date", "store_id", "sku_id", "yhat"]


class Forecaster(Protocol):
    name: str

    def fit(self, history: pd.DataFrame, skus: pd.DataFrame) -> Forecaster: ...

    def predict(self, history: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame: ...


def _demand_series(g: pd.DataFrame) -> np.ndarray:
    """Units with stockout days replaced by same-weekday recent mean (uncensoring)."""
    s = g.sort_values("date")
    y = s["units_sold"].astype(float).where(~s["stockout"].astype(bool))
    dow_fill = y.groupby(s["date"].dt.dayofweek).transform(lambda v: v.rolling(8, min_periods=1).mean().ffill())
    return y.fillna(dow_fill).fillna(0.0).to_numpy()


def _future_dates(future: pd.DataFrame, store: str, sku: str) -> pd.Series:
    return future.loc[(future.store_id == store) & (future.sku_id == sku), "date"].sort_values()


class SeasonalNaive:
    name = "seasonal_naive"

    def __init__(self, weeks: int = 1) -> None:
        self.weeks = weeks

    def fit(self, history: pd.DataFrame, skus: pd.DataFrame) -> SeasonalNaive:
        return self

    def predict(self, history: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
        out = []
        for (store, sku), g in history.groupby(KEYS, sort=False):
            y = _demand_series(g)
            dates = _future_dates(future, store, sku)
            last_dates = g.sort_values("date")["date"].iloc[-7 * self.weeks :]
            tail = y[-7 * self.weeks :].reshape(self.weeks, 7).mean(axis=0)
            by_dow = dict(zip(last_dates.dt.dayofweek.iloc[-7:], tail, strict=True))
            out.append(pd.DataFrame({"date": dates, "store_id": store, "sku_id": sku,
                                     "yhat": [by_dow[d.dayofweek] for d in dates]}))
        return pd.concat(out, ignore_index=True)[OUT_COLS]


def _ets_one(y: np.ndarray, h: int) -> np.ndarray:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    y = y[-365:]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ExponentialSmoothing(
                np.log1p(y), trend="add", damped_trend=True, seasonal="add", seasonal_periods=7,
                initialization_method="estimated",
            ).fit(optimized=True)
        fc = np.expm1(model.forecast(h))
        if not np.all(np.isfinite(fc)):
            raise ValueError("non-finite forecast")
        return np.clip(fc, 0, None)
    except Exception:
        return np.resize(y[-7:], h)  # seasonal-naive fallback, never fail a batch


class ETSLocal:
    name = "ets"

    def __init__(self, n_jobs: int = -1) -> None:
        self.n_jobs = n_jobs

    def fit(self, history: pd.DataFrame, skus: pd.DataFrame) -> ETSLocal:
        return self

    def predict(self, history: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
        groups = list(history.groupby(KEYS, sort=False))
        h = int(future.groupby(KEYS).size().max())
        preds = Parallel(n_jobs=self.n_jobs)(delayed(_ets_one)(_demand_series(g), h) for _, g in groups)
        out = []
        for ((store, sku), _), fc in zip(groups, preds, strict=True):
            dates = _future_dates(future, store, sku)
            out.append(pd.DataFrame({"date": dates.to_numpy(), "store_id": store, "sku_id": sku,
                                     "yhat": fc[: len(dates)]}))
        return pd.concat(out, ignore_index=True)[OUT_COLS]


def tsb_forecast(y: np.ndarray, alpha: float = 0.1, beta: float = 0.05) -> float:
    """Teunter-Syntetos-Babai: smooths demand probability and size separately.

    Unlike classic Croston it decays toward zero for obsolete items.
    """
    nz = y[y > 0]
    if len(nz) == 0:
        return 0.0
    p, z = float((y > 0).mean()), float(nz.mean())
    for v in y:
        if v > 0:
            z = z + alpha * (v - z)
            p = p + beta * (1 - p)
        else:
            p = p + beta * (0 - p)
    return p * z


class CrostonTSB:
    name = "croston_tsb"

    def fit(self, history: pd.DataFrame, skus: pd.DataFrame) -> CrostonTSB:
        return self

    def predict(self, history: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
        out = []
        for (store, sku), g in history.groupby(KEYS, sort=False):
            level = tsb_forecast(_demand_series(g)[-365:])
            dates = _future_dates(future, store, sku)
            out.append(pd.DataFrame({"date": dates, "store_id": store, "sku_id": sku, "yhat": level}))
        return pd.concat(out, ignore_index=True)[OUT_COLS]


class LightGBMGlobal:
    name = "lightgbm"

    def __init__(self, horizon: int, seed: int = 7, **params: object) -> None:
        self.horizon = horizon
        self.params: dict[str, object] = {
            "objective": "tweedie",           # counts with many zeros, right-skewed
            "tweedie_variance_power": 1.2,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_data_in_leaf": 40,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "lambda_l2": 1.0,
            "verbose": -1,
            "seed": seed,
            "num_threads": 0,
            **params,
        }
        self.num_boost_round = 400
        self.booster: lgb.Booster | None = None
        self.skus: pd.DataFrame | None = None
        self.categories: dict[str, list[str]] = {}
        self.features: list[str] = []  # exact training columns; saved with the model to catch skew

    def _align_categories(self, frame: pd.DataFrame) -> pd.DataFrame:
        for c, cats in self.categories.items():
            frame[c] = pd.Categorical(frame[c].astype(str), categories=cats)
        return frame

    def fit(self, history: pd.DataFrame, skus: pd.DataFrame) -> LightGBMGlobal:
        self.skus = skus
        frame = build_frame(history, None, skus, self.horizon)
        cols = self.features = feature_columns(self.horizon)
        train = frame[frame["units_sold"].notna() & ~frame["stockout"].astype(bool)]
        train = train[train["roll_mean_28"].notna()]
        self.categories = {c: list(map(str, frame[c].cat.categories)) for c in ("store_id", "sku_id", "category")}
        train = self._align_categories(train.copy())
        ds = lgb.Dataset(train[cols], label=train["units_sold"].astype(float), categorical_feature="auto",
                         free_raw_data=False)
        self.booster = lgb.train(self.params, ds, num_boost_round=self.num_boost_round)
        return self

    def predict(self, history: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
        if self.booster is None or self.skus is None:
            raise RuntimeError("fit() first")
        frame = build_frame(history, future, self.skus, self.horizon)
        fut = self._align_categories(frame[frame["is_future"]].copy())
        yhat = np.clip(self.booster.predict(fut[self.features]), 0, None)
        out = fut[["date", "store_id", "sku_id"]].copy()
        out["store_id"] = out["store_id"].astype(str)
        out["sku_id"] = out["sku_id"].astype(str)
        out["yhat"] = yhat
        return out.reset_index(drop=True)[OUT_COLS]

    def feature_importance(self, top: int = 10) -> dict[str, float]:
        if self.booster is None:
            return {}
        gain = self.booster.feature_importance("gain")
        names = self.booster.feature_name()
        total = gain.sum() or 1.0
        pairs = sorted(zip(names, gain / total, strict=True), key=lambda p: -p[1])[:top]
        return {n: round(float(v), 4) for n, v in pairs}


def candidate_models(horizon: int, seed: int = 7) -> list[Forecaster]:
    return [SeasonalNaive(), ETSLocal(), CrostonTSB(), LightGBMGlobal(horizon, seed=seed)]
