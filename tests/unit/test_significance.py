"""Promotion needs evidence, not luck: Diebold-Mariano on champion vs challenger backtest errors."""

import numpy as np
import pandas as pd

from kairos.forecasting.registry import evaluate_gates
from kairos.forecasting.significance import compare_forecasts


def _oof(noise: float, seed: int, n_days: int = 84) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-01-01", periods=n_days, freq="D")
    rows = pd.DataFrame([(d, s) for d in dates for s in ("S01", "S02")], columns=["date", "store_id"])
    rows["sku_id"] = "SKU001"
    rows["y"] = 20.0
    rows["yhat"] = 20.0 + rng.normal(0, noise, len(rows))
    rows["stockout"] = False
    return rows


def test_clearly_better_challenger_is_significant():
    r = compare_forecasts(_oof(noise=1.0, seed=1), _oof(noise=6.0, seed=2))
    assert r["p_value"] < 0.01 and r["mean_loss_diff"] < 0


def test_equally_good_challenger_is_not_significant():
    r = compare_forecasts(_oof(noise=3.0, seed=3), _oof(noise=3.0, seed=4))
    assert r["p_value"] > 0.05


def test_worse_challenger_has_high_one_sided_p_value():
    r = compare_forecasts(_oof(noise=6.0, seed=5), _oof(noise=1.0, seed=6))
    assert r["p_value"] > 0.95


def test_identical_forecasts_are_never_significant():
    a = _oof(noise=2.0, seed=7)
    assert compare_forecasts(a, a.copy())["p_value"] == 1.0


def test_stockout_rows_are_ignored():
    better, worse = _oof(1.0, 8), _oof(6.0, 9)
    worse.loc[:, "stockout"] = True  # nothing observable -> no evidence either way
    assert compare_forecasts(better, worse)["n"] == 0


def test_gate_requires_significance_when_a_champion_exists():
    m = {"coverage_empirical": 0.8, "mase": 0.7, "bias": 0.0, "wape": 0.30}
    champ = {**m, "wape": 0.40}
    lucky = {g.name: g.passed for g in evaluate_gates(m, champ, True, 0.8, 0.02, dm_p_value=0.40)}
    assert lucky["beats_champion"] and not lucky["significant_improvement"]
    real = {g.name: g.passed for g in evaluate_gates(m, champ, True, 0.8, 0.02, dm_p_value=0.01)}
    assert real["significant_improvement"]
