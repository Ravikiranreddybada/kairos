"""Read side of forecasting: serves published forecasts and what-if scenarios.

Training writes; this reads. Splitting them (CQRS-style) lets the API scale
horizontally with no model in memory except the small GBM used for what-if,
and lets training run as a separate job on its own schedule (ADR-0007).
"""

from __future__ import annotations

import dataclasses
import json
import threading
from dataclasses import dataclass
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from kairos.config import Settings
from kairos.data.warehouse import Warehouse
from kairos.forecasting.features import KEYS, build_frame, feature_columns, future_frame
from kairos.forecasting.models import LightGBMGlobal
from kairos.forecasting.monitor import assess
from kairos.forecasting.registry import Registry
from kairos.inventory.network import NodeDemand, demand_correlation, pooling
from kairos.inventory.policy import PolicyInput, decide, service_level_tradeoff, sigma_from_interval
from kairos.inventory.simulate import SimInput, simulate
from kairos.observability import get_logger

# Feature -> plain-language driver, so a planner reads "promotion +38%", not "on_promo".
DRIVER_GROUPS = {
    "recent demand level": ("lag_", "roll_", "dow_mean_8w"),
    "weekly & yearly seasonality": ("dow", "dom", "month", "doy_"),
    "festival": ("festival",),
    "promotion": ("on_promo", "promo_ended_3d"),
    "price": ("price_ratio",),
    "store & product identity": ("store_id", "sku_id", "category"),
}


def _driver(feature: str) -> str:
    if feature == "dow_mean_8w":
        return "recent demand level"
    for name, prefixes in DRIVER_GROUPS.items():
        if any(feature == p or feature.startswith(p) for p in prefixes):
            return name
    return "other"


log = get_logger(__name__)


class NotReady(RuntimeError):
    """No champion model published yet."""


class NotFound(KeyError):
    pass


@dataclass
class _Loaded:
    run_id: str
    manifest: dict[str, Any]
    gbm: LightGBMGlobal | None
    gbm_unavailable: str | None = None  # why the GBM cannot serve (e.g. train/serve feature skew)


class ForecastService:
    def __init__(self, wh: Warehouse, settings: Settings) -> None:
        self.wh = wh
        self.settings = settings
        self.registry = Registry(settings.registry_dir)
        self._loaded: _Loaded | None = None
        self._lock = threading.Lock()

    # -- model lifecycle -----------------------------------------------------
    def _current(self) -> _Loaded:
        champion = self.registry.champion()
        if champion is None:
            raise NotReady("no champion model; run `kairos train`")
        with self._lock:
            if self._loaded is None or self._loaded.run_id != champion:  # hot-reload on promotion
                manifest = self.registry.load_manifest(champion)
                gbm: LightGBMGlobal | None = None
                why: str | None = "champion has no gradient-boosting model"
                run_dir = self.registry.run_dir(champion)
                if (run_dir / "lightgbm.txt").exists():
                    meta = json.loads((run_dir / "lightgbm_meta.json").read_text())
                    gbm = LightGBMGlobal(meta["horizon"])
                    gbm.booster = lgb.Booster(model_str=(run_dir / "lightgbm.txt").read_text())
                    gbm.categories = meta["categories"]
                    gbm.features = meta.get("features") or gbm.booster.feature_name()
                    gbm.skus = self.wh.table("dim_sku")
                    # Train/serve skew: the model needs features this code version no longer builds.
                    missing = sorted(set(gbm.features) - set(feature_columns(gbm.horizon)))
                    why = None
                    if missing:
                        gbm, why = None, (f"champion {champion} was trained with features this version does "
                                          f"not build ({missing}); retrain to restore what-if and explanations")
                        log.warning("feature skew", fields={"run_id": champion, "missing": missing})
                self._loaded = _Loaded(champion, manifest, gbm, why)
            return self._loaded

    @property
    def data_version(self) -> str:
        return self.registry.champion() or "none"

    def model_card(self) -> dict[str, Any]:
        cur = self._current()
        m = cur.manifest
        return {"run_id": cur.run_id, "spec": m["spec"], "metrics": m["metrics"], "gates": m["gates"],
                "data": m["data"], "feature_importance": m.get("feature_importance", {}),
                "demand_patterns": m.get("demand_patterns", []),
                "significance_vs_champion": m.get("significance_vs_champion"),
                "gbm_unavailable": cur.gbm_unavailable}

    # -- queries -------------------------------------------------------------
    def forecast(self, store_id: str, sku_id: str, horizon_days: int = 28) -> dict[str, Any]:
        self._current()
        horizon_days = max(1, min(horizon_days, self.settings.horizon_days))
        df = self.wh.query(
            "SELECT date, yhat, lo, hi, model, run_id FROM fact_forecast WHERE store_id = ? AND sku_id = ? "
            "ORDER BY date LIMIT ?",
            [store_id, sku_id, horizon_days],
        )
        if df.empty:
            raise NotFound(f"no forecast for {store_id}/{sku_id}")
        return {
            "store_id": store_id,
            "sku_id": sku_id,
            "horizon_days": horizon_days,
            "total_units": round(float(df.yhat.sum()), 1),
            "total_lo": round(float(df.lo.sum()), 1),
            "total_hi": round(float(df.hi.sum()), 1),
            "interval": f"{round(100 * (1 - self.settings.interval_alpha))}%",
            "model": str(df.model.iloc[0]),
            "run_id": str(df.run_id.iloc[0]),
            "daily": [
                {"date": str(pd.Timestamp(r.date).date()), "yhat": round(r.yhat, 2), "lo": round(r.lo, 2),
                 "hi": round(r.hi, 2)}
                for r in df.itertuples()
            ],
        }

    def _policy_input(self, store_id: str, sku_id: str, service_level: float, lead_time_override: float | None
                      ) -> PolicyInput:
        row = self.wh.query(
            """
            SELECT k.unit_cost, k.holding_cost_rate_annual, s.lead_time_mean_days, s.lead_time_std_days,
                   s.moq_units, i.on_hand_units, i.on_order_units
            FROM dim_sku k JOIN dim_supplier s USING (supplier_id)
            JOIN fact_inventory i ON i.sku_id = k.sku_id AND i.store_id = ?
            WHERE k.sku_id = ?
            """,
            [store_id, sku_id],
        )
        if row.empty:
            raise NotFound(f"unknown store/sku {store_id}/{sku_id}")
        r = row.iloc[0]
        fc = self.forecast(store_id, sku_id, self.settings.horizon_days)
        L = float(lead_time_override or r.lead_time_mean_days)
        window = fc["daily"][: max(1, round(L))]
        d = sum(x["yhat"] for x in window) / len(window)
        sig = sum(sigma_from_interval(x["lo"], x["hi"], self.settings.interval_alpha) for x in window) / len(window)
        return PolicyInput(
            store_id=store_id, sku_id=sku_id, daily_mean=d, daily_sigma=sig, lead_time_mean=L,
            lead_time_std=float(r.lead_time_std_days), on_hand=float(r.on_hand_units),
            on_order=float(r.on_order_units), unit_cost=float(r.unit_cost),
            holding_rate_annual=float(r.holding_cost_rate_annual), moq=float(r.moq_units),
            service_level=service_level,
        )

    def inventory_policy(self, store_id: str, sku_id: str, service_level: float = 0.95,
                         lead_time_override: float | None = None) -> dict[str, Any]:
        p = self._policy_input(store_id, sku_id, service_level, lead_time_override)
        return {"decision": decide(p).to_dict(), "tradeoff": service_level_tradeoff(p),
                "inputs": {"daily_mean": round(p.daily_mean, 2), "daily_sigma": round(p.daily_sigma, 2),
                           "lead_time_mean": p.lead_time_mean, "lead_time_std": p.lead_time_std},
                "run_id": self.data_version}

    def what_if_promo(self, store_id: str, sku_id: str, start_date: str | None = None, days: int = 7
                      ) -> dict[str, Any]:
        cur = self._current()
        if cur.gbm is None:
            raise NotReady(f"what-if unavailable: {cur.gbm_unavailable}")
        hist = self.wh.sales()
        series = hist[(hist.store_id == store_id) & (hist.sku_id == sku_id)]
        if series.empty:
            raise NotFound(f"unknown store/sku {store_id}/{sku_id}")
        H = cur.gbm.horizon
        first = hist["date"].max() + pd.Timedelta(days=1)
        start = pd.Timestamp(start_date) if start_date else first
        start = min(max(start, first), first + pd.Timedelta(days=H - days))
        promo_days = pd.date_range(start, periods=days, freq="D")
        plan = pd.DataFrame({"store_id": store_id, "sku_id": sku_id, "date": promo_days})

        base_f = future_frame(hist, H)
        promo_f = future_frame(hist, H, plan)
        base = cur.gbm.predict(hist, base_f)
        promo = cur.gbm.predict(hist, promo_f)
        key = (base.store_id == store_id) & (base.sku_id == sku_id)
        b, p = base[key].set_index("date")["yhat"], promo[key].set_index("date")["yhat"]
        window = b.index.isin(promo_days)
        post = (b.index > promo_days[-1]) & (b.index <= promo_days[-1] + pd.Timedelta(days=3))
        base_units, promo_units = float(b[window].sum()), float(p[window].sum())
        dip = float(p[post].sum() - b[post].sum())
        return {
            "store_id": store_id, "sku_id": sku_id, "start_date": str(start.date()), "days": days,
            "baseline_units": round(base_units, 1), "promo_units": round(promo_units, 1),
            "uplift_pct": round(100 * (promo_units / base_units - 1), 1) if base_units else None,
            "post_promo_dip_units": round(dip, 1),
            "net_incremental_units": round(promo_units - base_units + dip, 1),
            "run_id": cur.run_id,
        }

    def explain(self, store_id: str, sku_id: str, horizon_days: int = 28) -> dict[str, Any]:
        """Why is the forecast what it is? Per-driver effects from the GBM's exact SHAP values.

        LightGBM computes TreeSHAP natively (``pred_contrib=True``). With a
        Tweedie (log-link) model contributions are additive in log space, so each
        driver is reported as a multiplier on a baseline day:

            typical_day = baseline x prod(1 + effect_pct/100)      (exact)

        where ``typical_day`` is the geometric mean of the daily predictions.
        """
        cur = self._current()
        if cur.gbm is None or cur.gbm.booster is None or cur.gbm.skus is None:
            raise NotReady(f"explanation unavailable: {cur.gbm_unavailable}")
        hist = self.wh.sales(store_id, sku_id)
        if hist.empty:
            raise NotFound(f"unknown store/sku {store_id}/{sku_id}")
        H = cur.gbm.horizon
        frame = build_frame(hist, future_frame(hist, H), cur.gbm.skus, H)
        fut = cur.gbm._align_categories(frame[frame["is_future"]].copy()).head(max(1, min(horizon_days, H)))
        cols = cur.gbm.features
        contrib = np.asarray(cur.gbm.booster.predict(fut[cols], pred_contrib=True))
        per_feature = pd.DataFrame(contrib[:, :-1], columns=cols).mean()
        bias = float(contrib[:, -1].mean())
        groups = per_feature.groupby(per_feature.index.map(_driver)).sum()
        drivers = [{"driver": g, "effect_pct": round(100 * (float(np.exp(v)) - 1), 2)}
                   for g, v in groups.sort_values(key=np.abs, ascending=False).items()]
        served = self.forecast(store_id, sku_id, horizon_days)
        return {
            "store_id": store_id, "sku_id": sku_id, "horizon_days": len(fut),
            "baseline_units_per_day": round(float(np.exp(bias)), 3),
            "model_units_per_day": round(float(np.exp(bias + per_feature.sum())), 3),
            "drivers": drivers,
            "explained_model": "lightgbm",
            "served_model": served["model"],
            "note": None if served["model"] in ("lightgbm", "ensemble") else
            f"served forecast comes from {served['model']}; drivers explain the gradient-boosting view",
            "run_id": cur.run_id,
        }

    def reorder_worklist(self, store_id: str, service_level: float = 0.95, top_k: int = 10
                         ) -> dict[str, Any]:
        """Every SKU at a store, ranked by stockout risk: the Monday-morning list."""
        skus = self.wh.query("SELECT DISTINCT sku_id FROM fact_forecast WHERE store_id = ? ORDER BY 1",
                             [store_id]).sku_id.tolist()
        if not skus:
            raise NotFound(f"no forecasts for store {store_id}")
        items = []
        for sku in skus:
            d = decide(self._policy_input(store_id, sku, service_level, None))
            items.append({"sku_id": sku, "stockout_probability": round(d.stockout_probability, 3),
                          "should_order": d.should_order, "order_qty": d.order_qty,
                          "inventory_position": round(d.inventory_position, 1),
                          "reorder_point": round(d.reorder_point, 1),
                          "days_of_cover": None if d.days_of_cover is None else round(d.days_of_cover, 1)})
        items.sort(key=lambda r: (-r["stockout_probability"], r["sku_id"]))
        top = items[:top_k]
        return {"store_id": store_id, "service_level": service_level, "skus_checked": len(items),
                "to_order": sum(r["should_order"] for r in top), "items": top, "run_id": self.data_version}

    def stress_test(self, store_id: str, sku_id: str, service_level: float = 0.95,
                    lead_time_delay_days: float = 0.0, demand_shock_pct: float = 0.0,
                    n_paths: int | None = None) -> dict[str, Any]:
        """Monte-Carlo the current (s, S) policy, as-is and under a supply/demand disruption."""
        p = self._policy_input(store_id, sku_id, service_level, None)
        dec = decide(p)
        fc = self.forecast(store_id, sku_id, self.settings.horizon_days)["daily"]
        mean = np.array([x["yhat"] for x in fc])
        sigma = np.array([sigma_from_interval(x["lo"], x["hi"], self.settings.interval_alpha) for x in fc])
        base = SimInput(daily_mean=mean, daily_sigma=sigma, on_hand=p.on_hand, on_order=p.on_order,
                        lead_time_mean=p.lead_time_mean, lead_time_std=p.lead_time_std,
                        reorder_point=dec.reorder_point, order_up_to=dec.reorder_point + p.daily_mean * p.review_days,
                        moq=p.moq, service_level=service_level, review_days=p.review_days,
                        n_paths=n_paths or self.settings.simulation_paths, seed=self.settings.seed)
        baseline = simulate(base)
        disrupted = bool(lead_time_delay_days or demand_shock_pct)
        scenario = simulate(dataclasses.replace(base, lead_time_delay_days=lead_time_delay_days,
                                                demand_shock_pct=demand_shock_pct)) if disrupted else baseline
        # Distribution-free order-now: cover the scenario's service-level lead-time demand plus one review period.
        shocked_daily = p.daily_mean * (1 + demand_shock_pct / 100)
        target = scenario.quantile_reorder_point + shocked_daily * p.review_days
        gap = target - dec.inventory_position
        order_now = float(np.ceil(max(gap, p.moq))) if gap > 0 else 0.0
        return {
            "store_id": store_id, "sku_id": sku_id, "service_level": service_level,
            "scenario": {"lead_time_delay_days": lead_time_delay_days, "demand_shock_pct": demand_shock_pct},
            "policy": {"reorder_point": round(dec.reorder_point, 1), "gaussian_safety_stock": round(dec.safety_stock, 1),
                       "inventory_position": round(dec.inventory_position, 1)},
            "baseline": baseline.to_dict(),
            "disrupted": scenario.to_dict() if disrupted else None,
            "stockout_risk_change_pts": round(100 * (scenario.prob_stockout_in_horizon - baseline.prob_stockout_in_horizon), 1),
            "distribution_free_reorder_point": round(scenario.quantile_reorder_point, 1),
            "recommended_order_now": order_now,
            "method": f"{base.n_paths} seeded Monte-Carlo paths, gamma-Poisson demand, gamma lead times, lost sales",
            "run_id": self.data_version,
        }

    def network_pooling(self, sku_id: str, service_level: float = 0.95,
                        dc_to_store_days: float | None = None) -> dict[str, Any]:
        """Safety stock if every store buys direct vs a DC holding one pooled buffer."""
        stores = self.wh.query("SELECT DISTINCT store_id FROM fact_forecast WHERE sku_id = ? ORDER BY 1",
                               [sku_id]).store_id.tolist()
        if len(stores) < 2:
            raise NotFound(f"pooling needs forecasts for {sku_id} at 2+ stores")
        inputs = [self._policy_input(s, sku_id, service_level, None) for s in stores]
        corr = demand_correlation(self.wh.sales(sku_id=sku_id), stores)
        first = inputs[0]
        out = pooling([NodeDemand(p.store_id, p.daily_mean, p.daily_sigma) for p in inputs], corr,
                      first.lead_time_mean, first.lead_time_std, service_level,
                      dc_to_store_days or self.settings.dc_to_store_days, first.unit_cost, first.holding_rate_annual)
        return {"sku_id": sku_id, **out, "run_id": self.data_version}

    def model_health(self, top_k: int = 5) -> dict[str, Any]:
        cur = self._current()
        fc = self.wh.query("SELECT store_id, sku_id, yhat FROM fact_forecast")
        return assess(self.wh.sales(), fc, {**cur.manifest, "run_id": cur.run_id}, top_k=top_k)

    def stores_skus(self) -> pd.DataFrame:
        return self.wh.query("SELECT DISTINCT store_id, sku_id FROM fact_forecast ORDER BY 1, 2")[KEYS]
