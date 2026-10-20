"""End-to-end training pipeline.

    validate -> backtest candidates -> select per segment -> calibrate intervals
             -> refit on full history -> forecast -> reconcile hierarchy
             -> gate -> register -> (promote) -> publish to warehouse

Each step is a plain function so an orchestrator (Prefect, Airflow, ZenML)
can wrap them as tasks without code changes (ADR-0007).
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from kairos.config import Settings
from kairos.data.contracts import validate_sales
from kairos.data.warehouse import Warehouse
from kairos.forecasting.backtest import backtest
from kairos.forecasting.conformal import ConformalCalibrator, evaluate_coverage, series_scales
from kairos.forecasting.features import feature_columns, future_frame
from kairos.forecasting.foundation import FoundationForecaster
from kairos.forecasting.metrics import summarize
from kairos.forecasting.models import (
    CrostonTSB,
    ETSLocal,
    Forecaster,
    LightGBMGlobal,
    SeasonalNaive,
    _ets_one,
)
from kairos.forecasting.reconcile import reconcile_frame
from kairos.forecasting.registry import Registry, evaluate_gates
from kairos.forecasting.segmentation import classify_demand, model_segment
from kairos.forecasting.significance import compare_forecasts
from kairos.observability import get_logger, span

log = get_logger(__name__)
SEGMENTS = ("regular", "intermittent")


@dataclass
class TrainResult:
    run_id: str
    promoted: bool
    spec: dict[str, str]
    metrics: dict[str, float]
    leaderboard: list[dict[str, Any]]
    gates: list[dict[str, Any]]
    feature_importance: dict[str, float] = field(default_factory=dict)


def fingerprint(df: pd.DataFrame) -> str:
    h = hashlib.sha256(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes())
    return h.hexdigest()[:16]


Segments = dict[tuple[str, str], str]


def _segment(df: pd.DataFrame, segs: Segments) -> np.ndarray:
    """Model-selection segment per row, from data-driven ADI/CV² classes (see ``segmentation``)."""
    return np.array([segs.get(k, "regular") for k in zip(df["store_id"], df["sku_id"], strict=True)])


def _models(settings: Settings) -> dict[str, Forecaster]:
    models: dict[str, Forecaster] = {
        "seasonal_naive": SeasonalNaive(),
        "ets": ETSLocal(),
        "croston_tsb": CrostonTSB(),
        "lightgbm": LightGBMGlobal(settings.horizon_days, seed=settings.seed),
    }
    if settings.foundation_model != "none":
        # A pretrained model is one more candidate: it ships only if it wins the backtest and gates (ADR-0018).
        if importlib.util.find_spec("chronos") is None:
            log.warning("foundation model requested but not installed; pip install -e '.[foundation]'",
                        fields={"foundation_model": settings.foundation_model})
        else:
            models[settings.foundation_model] = FoundationForecaster(
                settings.foundation_model, settings.foundation_model_id)
    return models


def _with_ensemble(preds: dict[str, pd.DataFrame], cols: list[str]) -> dict[str, pd.DataFrame]:
    """Equal-weight ETS+GBM blend: diversifies model error at zero training cost."""
    if {"ets", "lightgbm"} <= preds.keys():
        a, b = preds["ets"], preds["lightgbm"]
        ens = a[cols].merge(b[[*cols[:3], "yhat"]], on=cols[:3], suffixes=("_ets", "_gbm"))
        ens["yhat"] = 0.5 * ens["yhat_ets"] + 0.5 * ens["yhat_gbm"]
        preds["ensemble"] = ens.drop(columns=["yhat_ets", "yhat_gbm"])
    return preds


def compose(preds: dict[str, pd.DataFrame], spec: dict[str, str], segs: Segments) -> pd.DataFrame:
    parts = []
    for seg, name in spec.items():
        p = preds[name]
        parts.append(p[_segment(p, segs) == seg].assign(model=name))
    return pd.concat(parts, ignore_index=True)


def score_spec(oof: dict[str, pd.DataFrame], spec: dict[str, str], segs: Segments,
               scales: pd.Series, alpha: float) -> dict[str, float]:
    combined = compose(oof, spec, segs)
    m = summarize(combined, scales)
    cov = evaluate_coverage(combined, scales, alpha)
    return {**m, "coverage_empirical": cov["empirical"], "interval_width": cov["mean_width"]}


def train(wh: Warehouse, settings: Settings, promote: bool = True) -> TrainResult:
    registry = Registry(settings.registry_dir)
    sales, skus = wh.sales(), wh.table("dim_sku")
    H, alpha = settings.horizon_days, settings.interval_alpha

    with span("pipeline.validate"):
        quality = validate_sales(sales)
    if not quality.passed:
        raise ValueError(f"data contract failed: {json.dumps(quality.to_dict())}")

    scales = series_scales(sales)
    patterns = classify_demand(sales)
    segs: Segments = {(r.store_id, r.sku_id): model_segment(r.pattern) for r in patterns.itertuples()}
    models = _models(settings)

    with span("pipeline.backtest", models=list(models)):
        oof = {name: backtest(m, sales, skus, H, settings.backtest_folds) for name, m in models.items()}
        oof = _with_ensemble(oof, ["date", "store_id", "sku_id", "h", "fold", "y", "stockout", "yhat"])

    leaderboard = []
    for name, df in oof.items():
        seg = _segment(df, segs)
        for s in SEGMENTS:
            m = summarize(df[seg == s], scales)
            leaderboard.append({"model": name, "segment": s, **{k: round(v, 4) for k, v in m.items()}})
    lb = pd.DataFrame(leaderboard)
    spec = {s: str(lb[lb.segment == s].sort_values("wape").iloc[0]["model"]) for s in SEGMENTS}
    metrics = score_spec(oof, spec, segs, scales, alpha)

    champion_id = registry.champion()
    champion_metrics = None
    significance: dict[str, Any] | None = None
    unservable = _unservable_reason(registry, champion_id, H) if champion_id else None
    if champion_id and not unservable:
        champ_spec = registry.load_manifest(champion_id)["spec"]
        champ_spec = {k: v for k, v in champ_spec.items() if k in SEGMENTS}
        if all(v in oof for v in champ_spec.values()):
            champion_metrics = score_spec(oof, champ_spec, segs, scales, alpha)
            significance = compare_forecasts(compose(oof, spec, segs), compose(oof, champ_spec, segs))

    gates = evaluate_gates(metrics, champion_metrics, quality.passed, 1 - alpha,
                           settings.promotion_min_improvement,
                           dm_p_value=significance["p_value"] if significance else None,
                           champion_unservable=unservable)

    with span("pipeline.calibrate"):
        calibrator = ConformalCalibrator(alpha=alpha).fit(compose(oof, spec, segs), scales)

    with span("pipeline.refit_and_forecast", spec=spec):
        future = future_frame(sales, H)
        fit_names: set[str] = set()
        for name in spec.values():
            fit_names |= {"ets", "lightgbm"} if name == "ensemble" else {name}
        preds: dict[str, pd.DataFrame] = {}
        gbm: LightGBMGlobal | None = None
        for name in fit_names:
            model = _models(settings)[name]
            model.fit(sales, skus)
            preds[name] = model.predict(sales, future)
            if isinstance(model, LightGBMGlobal):
                gbm = model
        preds = _with_ensemble(preds, ["date", "store_id", "sku_id", "yhat"])
        bottom = compose(preds, spec, segs)

    with span("pipeline.reconcile"):
        upper = _upper_level_forecasts(sales, H)
        coherent = reconcile_frame(bottom[["date", "store_id", "sku_id", "yhat"]], upper)
        bottom_rec = coherent[coherent.node.str.contains("|", regex=False)].copy()
        bottom_rec[["store_id", "sku_id"]] = bottom_rec["node"].str.split("|", expand=True)
        bottom = bottom.drop(columns="yhat").merge(
            bottom_rec[["date", "store_id", "sku_id", "yhat"]], on=["date", "store_id", "sku_id"]
        )
        h = (bottom["date"] - sales["date"].max()).dt.days
        bottom = calibrator.apply(bottom, h)

    run_id = registry.new_run_id()
    bottom["run_id"] = run_id
    rounded = {k: round(float(v), 5) for k, v in metrics.items()}
    importance = gbm.feature_importance() if gbm else {}
    manifest: dict[str, Any] = {
        "spec": {**spec, "horizon_days": H, "alpha": alpha},
        "metrics": rounded,
        "champion_metrics_same_folds": champion_metrics,
        "significance_vs_champion": significance,
        "leaderboard": leaderboard,
        "gates": [g.__dict__ for g in gates],
        "data": {"fingerprint": fingerprint(sales), "rows": len(sales),
                 "start": str(sales.date.min().date()), "end": str(sales.date.max().date())},
        "feature_importance": importance,
        "demand_patterns": patterns.to_dict(orient="records"),
    }
    files: dict[str, str | bytes] = {
        "calibrator.json": json.dumps({"alpha": alpha, "quantiles": calibrator.quantiles,
                                       "scales": {f"{k[0]}|{k[1]}": v for k, v in calibrator.scales.items()}}),
        "quality.json": json.dumps(quality.to_dict(), indent=2),
    }
    # Snapshot of exactly what this run would serve, so a rollback can re-serve it.
    files["forecast.csv"] = bottom[FORECAST_COLS].to_csv(index=False)
    files["hierarchy.csv"] = coherent.assign(run_id=run_id)[HIERARCHY_COLS].to_csv(index=False)
    if gbm and gbm.booster is not None:
        files["lightgbm.txt"] = gbm.booster.model_to_string()
        files["lightgbm_meta.json"] = json.dumps({"categories": gbm.categories, "horizon": H,
                                                   "features": gbm.features})
    registry.save_run(run_id, manifest, files)

    passed = all(g.passed for g in gates)
    promoted = bool(promote and passed)
    if promoted:
        registry.promote(run_id, reason="; ".join(g.detail for g in gates))
        _publish(wh, bottom, coherent.assign(run_id=run_id))
    log.info("training finished", fields={"run_id": run_id, "promoted": promoted, "spec": spec,
                                          "wape": metrics["wape"]})
    return TrainResult(run_id, promoted, spec, rounded, leaderboard, [g.__dict__ for g in gates], importance)


def _unservable_reason(registry: Registry, run_id: str, horizon: int) -> str | None:
    """A champion this code cannot run (feature skew) is no baseline: comparing against it would
    block every retrain forever while what-if and explanations stay broken."""
    meta_path = registry.run_dir(run_id) / "lightgbm_meta.json"
    if not meta_path.exists():
        return None
    trained_on = json.loads(meta_path.read_text()).get("features")
    if trained_on is None:
        return "no feature list saved (trained by an older version)"
    missing = sorted(set(trained_on) - set(feature_columns(horizon)))
    return f"needs features this version does not build: {missing}" if missing else None


def _upper_level_forecasts(sales: pd.DataFrame, H: int) -> pd.DataFrame:
    """ETS base forecasts on aggregates. Aggregates are smooth, so ETS is strong there."""
    clean = sales.assign(units=sales["units_sold"].where(~sales["stockout"]))
    start = sales["date"].max() + pd.Timedelta(days=1)
    dates = pd.date_range(start, periods=H, freq="D")
    rows = []
    total = clean.groupby("date")["units"].sum().to_numpy()
    rows.append(pd.DataFrame({"date": dates, "node": "total", "yhat": _ets_one(total, H)}))
    for store, g in clean.groupby("store_id"):
        y = g.groupby("date")["units"].sum().to_numpy()
        rows.append(pd.DataFrame({"date": dates, "node": f"store:{store}", "yhat": _ets_one(y, H)}))
    return pd.concat(rows, ignore_index=True)


def publish_run(wh: Warehouse, registry: Registry, run_id: str) -> None:
    """Serve a registered run's forecast snapshot (used by rollback and manual promotion)."""
    def read(name: str) -> pd.DataFrame:
        return pd.read_csv(io.StringIO(registry.read_file(run_id, name)), parse_dates=["date"],
                           dtype={"run_id": str})

    _publish(wh, read("forecast.csv"), read("hierarchy.csv"))


def rollback(wh: Warehouse, settings: Settings) -> str:
    """Restore the previous champion *and* the forecasts it produced.

    Flipping ``champion.json`` alone would leave planners reading the newer
    run's numbers under the older run's id: provenance silently wrong.
    """
    registry = Registry(settings.registry_dir)
    current = registry.champion()
    previous = registry.rollback()
    try:
        publish_run(wh, registry, previous)
    except FileNotFoundError:
        if current:
            registry.promote(current, reason="rollback aborted: previous run has no forecast snapshot")
        raise
    log.info("rolled back", fields={"from": current, "to": previous})
    return previous


FORECAST_COLS = ["date", "store_id", "sku_id", "yhat", "lo", "hi", "model", "run_id"]
HIERARCHY_COLS = ["date", "node", "yhat", "run_id"]


def _publish(wh: Warehouse, bottom: pd.DataFrame, coherent: pd.DataFrame) -> None:
    """Atomically replace the served forecast tables (readers see old or new, never half).

    The only writer of ``fact_forecast`` (CLAUDE.md invariant 3).
    """
    with wh.cursor() as cur:
        cur.register("_fc", bottom[FORECAST_COLS])
        cur.register("_node", coherent[HIERARCHY_COLS])
        cur.execute("BEGIN TRANSACTION")
        cur.execute("CREATE OR REPLACE TABLE fact_forecast AS SELECT * FROM _fc")
        cur.execute("CREATE OR REPLACE TABLE fact_forecast_hierarchy AS SELECT * FROM _node")
        cur.execute("COMMIT")
        cur.unregister("_fc")
        cur.unregister("_node")
