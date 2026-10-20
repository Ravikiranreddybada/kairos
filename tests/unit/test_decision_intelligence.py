"""Fast unit tests for the v2 decision layer: supply twin, network pooling, drift, ledger, doc tree, foundation."""

import math

import numpy as np
import pandas as pd
import pytest

from kairos.decisions.ledger import DecisionLedger, LedgerError
from kairos.forecasting.foundation import FoundationForecaster
from kairos.forecasting.monitor import assess, psi, psi_noise_floor
from kairos.inventory.network import NodeDemand, demand_correlation, pooling
from kairos.inventory.policy import PolicyInput, decide
from kairos.inventory.simulate import SimInput, sample_demand, sample_lead_times, simulate
from kairos.rag.tree import DocTree, parse


# ------------------------------------------------------------------ supply twin
def _sim(**kw):
    base = dict(daily_mean=np.full(28, 20.0), daily_sigma=np.full(28, 6.0), on_hand=200, on_order=0,
                lead_time_mean=5, lead_time_std=1, reorder_point=130, order_up_to=270, n_paths=3000, seed=1)
    return simulate(SimInput(**{**base, **kw}))


def test_sampled_demand_matches_forecast_mean_and_variance():
    rng = np.random.default_rng(0)
    d = sample_demand(rng, np.full(5, 20.0), np.full(5, 8.0), 40_000)
    assert d.mean() == pytest.approx(20, rel=0.02)
    assert d.std() == pytest.approx(8, rel=0.05)
    assert (d >= 0).all() and np.allclose(d, np.round(d))  # count demand


def test_lead_times_are_whole_days_with_the_right_mean():
    lt = sample_lead_times(np.random.default_rng(0), 7.0, 2.0, 50_000)
    assert lt.min() >= 1 and lt.dtype.kind == "i"
    assert lt.mean() == pytest.approx(7.0, abs=0.1)


def test_simulation_is_deterministic_and_bounded():
    a, b = _sim(), _sim()
    assert a == b
    assert 0 <= a.prob_stockout_in_horizon <= 1 and 0 <= a.fill_rate <= 1
    assert a.ending_on_hand_p10 <= a.ending_on_hand_p50 <= a.ending_on_hand_p90


def test_disruptions_make_things_worse_monotonically():
    base, late, later = _sim(), _sim(lead_time_delay_days=5), _sim(lead_time_delay_days=12)
    assert base.fill_rate >= late.fill_rate >= later.fill_rate
    assert base.expected_lost_units <= late.expected_lost_units <= later.expected_lost_units
    hot = _sim(demand_shock_pct=50)
    assert hot.expected_lost_units > base.expected_lost_units


def test_distribution_free_rop_tracks_gaussian_rop_for_well_behaved_demand():
    p = PolicyInput("S", "K", daily_mean=20, daily_sigma=6, lead_time_mean=5, lead_time_std=1, on_hand=200,
                    on_order=0, unit_cost=1, service_level=0.95)
    gaussian = decide(p).reorder_point
    sim = _sim(n_paths=20_000)
    # Same quantile of the same lead-time demand; gamma-Poisson + whole-day lead times add mild skew.
    assert sim.quantile_reorder_point == pytest.approx(gaussian, rel=0.15)


def test_no_demand_means_no_stockouts_and_no_orders():
    r = _sim(daily_mean=np.zeros(28), daily_sigma=np.zeros(28), reorder_point=0, order_up_to=0)
    assert r.prob_stockout_in_horizon == 0 and r.expected_orders == 0 and r.fill_rate == 1.0


# -------------------------------------------------------------- network pooling
def _nodes(n=4):
    return [NodeDemand(f"S{i:02d}", 20.0, 6.0) for i in range(1, n + 1)]


def test_pooling_follows_square_root_law_when_independent_and_no_lead_time_variance():
    out = pooling(_nodes(4), np.eye(4), lead_time_mean=9, lead_time_std=0, service_level=0.95,
                  dc_to_store_days=1e-9, unit_cost=1, holding_rate_annual=0.25)
    # 4 identical independent stores: pooled buffer = sqrt(4) x one store = half of the sum.
    assert out["dc_pooled_ss"] == pytest.approx(out["store_direct_total_ss"] / 2, rel=0.01)
    assert out["pct_saved"] == pytest.approx(50, abs=1)


def test_perfectly_correlated_demand_pools_nothing():
    out = pooling(_nodes(3), np.ones((3, 3)), 9, 0, 0.95, 1e-9, 1, 0.25)
    assert out["dc_pooled_ss"] == pytest.approx(out["store_direct_total_ss"], rel=0.01)


def test_lead_time_variance_does_not_pool_and_break_even_is_consistent():
    out = pooling(_nodes(4), np.eye(4), 7, 3, 0.95, 2, 1, 0.25)
    assert out["lead_time_variance_share"] > 0.5 and "supplier" in out["verdict"]
    if out["break_even_dc_to_store_days"] > 0:
        at_break_even = pooling(_nodes(4), np.eye(4), 7, 3, 0.95, out["break_even_dc_to_store_days"], 1, 0.25)
        assert at_break_even["units_saved"] == pytest.approx(0, abs=1)


def test_demand_correlation_ignores_stockout_days():
    dates = pd.date_range("2026-01-01", periods=200)
    rng = np.random.default_rng(0)
    common = rng.normal(0, 5, len(dates))
    rows = []
    for s in ("S01", "S02"):
        units = 50 + common + rng.normal(0, 1, len(dates))
        out = np.zeros(len(dates), bool)
        if s == "S02":
            out[::10] = True
            units[out] = 0  # censored: must not break the correlation
        rows.append(pd.DataFrame({"date": dates, "store_id": s, "units_sold": units, "stockout": out}))
    corr = demand_correlation(pd.concat(rows), ["S01", "S02"])
    assert corr[0, 1] > 0.9


# ------------------------------------------------------------------- drift
def test_psi_is_near_zero_for_same_distribution_and_large_for_a_shift():
    rng = np.random.default_rng(0)
    ref = rng.poisson(20, 2000)
    assert psi(ref, rng.poisson(20, 2000)) < 0.02
    assert psi(ref, rng.poisson(35, 500)) > 0.25


def test_noise_floor_absorbs_small_sample_psi():
    rng = np.random.default_rng(1)
    ref = rng.poisson(20, 182).astype(float)
    floor = psi_noise_floor(ref, 28, np.random.default_rng(2))
    # A same-distribution 28-day sample is typically below its own noise floor.
    assert psi(ref, rng.poisson(20, 28)) < floor * 1.5


def test_assess_flags_a_level_shift_but_not_a_stable_series():
    dates = pd.date_range("2025-01-01", periods=300)
    rng = np.random.default_rng(3)
    stable = rng.poisson(20, 300).astype(float)
    shifted = np.r_[rng.poisson(20, 272), rng.poisson(40, 28)].astype(float)
    sales = pd.concat([pd.DataFrame({"date": dates, "store_id": "S01", "sku_id": k, "units_sold": y,
                                     "stockout": False}) for k, y in (("SKU001", stable), ("SKU002", shifted))])
    fc = pd.DataFrame({"store_id": "S01", "sku_id": ["SKU001", "SKU002"], "yhat": [20.0, 20.0]})
    out = assess(sales, fc, {"run_id": "r1", "metrics": {"wape": 0.3}}, top_k=2)
    by = {w["sku_id"]: w for w in out["worst"]}
    assert by["SKU002"]["level_shift"] and by["SKU002"]["drifting"]
    assert not by["SKU001"]["level_shift"]
    assert out["series_level_shifted"] == 1 and out["status"] == "retrain_recommended"


# ------------------------------------------------------------------ ledger
def _snapshot(qty=100.0, ss=50.0, ip=80.0):
    return {"run_id": "run-1", "decision": {"store_id": "S01", "sku_id": "SKU002", "order_qty": qty,
                                            "safety_stock": ss, "inventory_position": ip, "reorder_point": 120,
                                            "stockout_probability": 0.2, "service_level": 0.95,
                                            "rationale": "test"}}


def test_four_eyes_rule_and_single_decision():
    led = DecisionLedger()
    p = led.propose(_snapshot(), actor="planner")
    assert p["status"] == "pending"
    with pytest.raises(LedgerError, match="four-eyes"):
        led.decide(p["id"], True, actor="planner")
    led.decide(p["id"], True, actor="approver")
    with pytest.raises(LedgerError, match="already"):
        led.decide(p["id"], False, actor="approver2")


def test_override_needs_a_reason_and_outcome_needs_approval():
    led = DecisionLedger()
    p = led.propose(_snapshot(), actor="planner")
    with pytest.raises(LedgerError, match="reason"):
        led.decide(p["id"], True, actor="approver", qty=150)
    rejected = led.propose(_snapshot(), actor="planner")
    led.decide(rejected["id"], False, actor="approver", reason="budget freeze")
    with pytest.raises(LedgerError, match="approved"):
        led.record_outcome(rejected["id"], 100, actor="erp")


def test_audit_chain_detects_tampering():
    led = DecisionLedger()
    p = led.propose(_snapshot(), actor="planner")
    led.decide(p["id"], True, actor="approver", qty=120, reason="festival")
    assert led.verify_chain() == {**led.verify_chain(), "ok": True, "entries": 2}
    led._con.execute("UPDATE audit SET data = ? WHERE seq = 2", ('{"final_qty":999,"reason":"festival"}',))
    bad = led.verify_chain()
    assert not bad["ok"] and bad["broken_at_seq"] == 2


def test_lessons_accumulate_evidence_and_score_override_value_add():
    led = DecisionLedger()
    for _ in range(3):  # planners raise 100 -> 130; reality needed ~ 130
        p = led.propose(_snapshot(qty=100, ss=50, ip=80), actor="planner")
        led.decide(p["id"], True, actor="approver", qty=130, reason="local event")
        # ideal = actual + ss - ip = 160 + 50 - 80 = 130
        led.record_outcome(p["id"], 160, actor="erp")
    lesson = led.lessons("S01", "SKU002")[0]
    assert lesson["decisions"] == 3 and lesson["overrides"] == 3 and lesson["outcomes"] == 3
    assert lesson["override_direction"] == "raise" and lesson["mean_override_pct"] == pytest.approx(30)
    assert lesson["override_value_add_pct"] == pytest.approx(100)  # planner error 0 vs model error 30
    assert lesson["confidence"] == "medium" and len(lesson["evidence"]) == 3
    # New contrary evidence refines the belief instead of overwriting it.
    p = led.propose(_snapshot(qty=100, ss=50, ip=80), actor="planner")
    led.decide(p["id"], True, actor="approver", qty=130, reason="local event")
    led.record_outcome(p["id"], 130, actor="erp")  # ideal 100: the override was wrong this time
    refined = led.lessons("S01", "SKU002")[0]
    assert refined["outcomes"] == 4 and 0 < refined["override_value_add_pct"] < 100


# --------------------------------------------------------------- doc tree
def test_doc_tree_outline_section_and_injection_sanitising():
    tree = DocTree.from_dir()
    outline = tree.browse()
    ids = {d["node_id"] for d in outline["documents"]}
    assert {"inventory_policy", "supplier_contracts", "vendor_portal_note"} <= ids
    section = tree.browse("inventory_policy#Safety stock method")
    assert "sigma_L" in section["text"] and section["cite_as"] == "inventory_policy#Safety stock method"
    poisoned = tree.browse("vendor_portal_note#Delivery update")
    assert poisoned["untrusted"] and "ignore" not in poisoned["text"].lower()
    with pytest.raises(LookupError):
        tree.browse("nope#nothing")


def test_parse_handles_preamble_and_sections():
    root = parse("doc", "# Title\n\nIntro line. More.\n\n## A\n\nAlpha text.\n\n## B\n\nBeta text.")
    assert root.title == "Title" and root.summary == "Intro line."
    assert [c.id for c in root.children] == ["doc#A", "doc#B"]


# -------------------------------------------------------------- foundation
def test_foundation_forecaster_uses_uncensored_context_and_aligns_dates():
    dates = pd.date_range("2026-01-01", periods=60)
    hist = pd.DataFrame({"date": dates, "store_id": "S01", "sku_id": "SKU001",
                         "units_sold": np.r_[np.full(59, 10.0), 0.0], "stockout": np.r_[np.zeros(59, bool), True]})
    future = pd.DataFrame({"date": pd.date_range("2026-03-02", periods=7), "store_id": "S01", "sku_id": "SKU001"})
    seen: list[np.ndarray] = []

    def predictor(ctx, h):
        seen.extend(ctx)
        return np.stack([np.full(h, c[-1]) for c in ctx])

    out = FoundationForecaster(predictor=predictor).fit(hist, pd.DataFrame()).predict(hist, future)
    assert list(out.columns) == ["date", "store_id", "sku_id", "yhat"] and len(out) == 7
    assert seen[0][-1] == pytest.approx(10.0)  # the stockout zero was un-censored before the model saw it
    assert math.isclose(out["yhat"].iloc[0], 10.0)


def test_pipeline_skips_foundation_model_when_not_installed(monkeypatch):
    import importlib.util

    from kairos.config import Settings
    from kairos.forecasting import pipeline

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert "chronos" not in pipeline._models(Settings(foundation_model="chronos"))
    assert "chronos" not in pipeline._models(Settings())
