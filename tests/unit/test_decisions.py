import math

import pytest

from kairos.anomaly.detector import DetectorConfig, detect, evaluate
from kairos.data.contracts import validate_sales
from kairos.forecasting.registry import Registry, evaluate_gates
from kairos.inventory.policy import PolicyInput, decide, service_level_tradeoff, sigma_from_interval


def _p(**kw):
    base = dict(store_id="S01", sku_id="SKU001", daily_mean=40, daily_sigma=12, lead_time_mean=7,
                lead_time_std=2, on_hand=180, on_order=0, unit_cost=120, moq=100)
    return PolicyInput(**{**base, **kw})


def test_safety_stock_uses_combined_variance():
    d = decide(_p())
    expected = 1.6449 * math.sqrt(7 * 12**2 + 40**2 * 2**2)
    assert d.safety_stock == pytest.approx(expected, rel=1e-3)
    assert d.reorder_point == pytest.approx(40 * 7 + expected, rel=1e-3)


def test_lead_time_variability_increases_safety_stock():
    assert decide(_p(lead_time_std=4)).safety_stock > decide(_p(lead_time_std=0)).safety_stock


def test_order_respects_moq_and_triggers_below_rop():
    d = decide(_p(on_hand=10, moq=5000))
    assert d.should_order and d.order_qty >= 5000
    assert not decide(_p(on_hand=10_000)).should_order


def test_service_level_curve_is_monotonic():
    ss = [r["safety_stock"] for r in service_level_tradeoff(_p())]
    assert ss == sorted(ss)


def test_sigma_from_interval_roundtrip():
    assert sigma_from_interval(-12.8155, 12.8155, 0.2) == pytest.approx(10.0, rel=1e-3)


def test_invalid_service_level_rejected():
    with pytest.raises(ValueError):
        decide(_p(service_level=1.0))


def test_contracts_catch_bad_data(dataset):
    bad = dataset.sales.copy()
    bad.loc[0, "units_sold"] = -5
    bad = __import__("pandas").concat([bad, bad.iloc[[1]]])
    report = validate_sales(bad)
    failing = {c.name for c in report.checks if c.severity == "error"}
    assert not report.passed and {"units.non_negative", "grain.unique"} <= failing
    assert validate_sales(dataset.sales).passed


def test_anomaly_detector_finds_injected_anomalies(dataset):
    flags = detect(dataset.sales, DetectorConfig(threshold=5.0))
    scores = evaluate(flags, dataset.anomalies)
    assert scores["precision"] >= 0.6 and scores["recall"] >= 0.5
    assert (flags.explained_by == "promotion").any()  # promos are attributed, not alerted


def test_promotion_gates(tmp_path):
    good = {"wape": 0.30, "mase": 0.7, "bias": 0.01, "coverage_empirical": 0.82}
    assert all(g.passed for g in evaluate_gates(good, None, True, 0.8, 0.02))
    worse = evaluate_gates(good, {"wape": 0.30}, True, 0.8, 0.02)
    assert not next(g for g in worse if g.name == "beats_champion").passed
    miscal = evaluate_gates({**good, "coverage_empirical": 0.6}, None, True, 0.8, 0.02)
    assert not next(g for g in miscal if g.name == "interval_calibration").passed
    assert not next(g for g in evaluate_gates(good, None, False, 0.8, 0.02) if g.name == "data_quality").passed


def test_registry_promote_and_rollback(tmp_path):
    reg = Registry(tmp_path)
    for rid in ("r1", "r2"):
        reg.save_run(rid, {"spec": {}, "metrics": {}}, {"x.txt": "1"})
        reg.promote(rid, "test")
    assert reg.champion() == "r2"
    assert reg.rollback() == "r1" and reg.champion() == "r1"


def test_zero_demand_decision_is_json_safe():
    import json

    d = decide(_p(daily_mean=0.0, daily_sigma=0.0)).to_dict()
    json.dumps(d, allow_nan=False)  # what FastAPI does; inf here used to be a 500
    assert d["days_of_cover"] is None and d["should_order"] is False
    empty = decide(_p(daily_mean=0.0, daily_sigma=0.0, on_hand=0)).to_dict()
    assert empty["should_order"] is False and empty["order_qty"] == 0
