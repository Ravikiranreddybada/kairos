import itertools

import numpy as np
import pandas as pd
import pytest

from kairos.forecasting.backtest import make_folds
from kairos.forecasting.conformal import ConformalCalibrator
from kairos.forecasting.features import build_frame, feature_columns, lag_set
from kairos.forecasting.metrics import bias, mase_scale, pinball, summarize, wape
from kairos.forecasting.models import tsb_forecast
from kairos.forecasting.reconcile import reconcile, summing_matrix


def test_wape_and_bias():
    y, yhat = np.array([10.0, 0.0, 30.0]), np.array([12.0, 1.0, 27.0])
    assert wape(y, yhat) == pytest.approx(6 / 40)
    assert bias(y, yhat) == pytest.approx(0.0)
    assert np.isnan(wape(np.zeros(3), np.ones(3)))


def test_mase_scale_is_seasonal_naive_error():
    y = np.tile([1.0, 2, 3, 4, 5, 6, 7], 4)
    assert mase_scale(y, 7) == 1.0  # perfect weekly pattern -> zero error -> floor at 1


def test_pinball_penalises_under_forecast_at_high_quantile():
    y = np.array([10.0])
    assert pinball(y, np.array([5.0]), 0.9) > pinball(y, np.array([15.0]), 0.9)


def test_summarize_excludes_stockout_days():
    df = pd.DataFrame({"y": [10, 0], "yhat": [10, 50], "stockout": [False, True]})
    assert summarize(df)["wape"] == 0.0


def test_horizon_safe_lags_are_never_shorter_than_horizon():
    for h in (1, 7, 14, 28):
        assert min(lag_set(h)) >= h


def test_features_do_not_leak_future_target(dataset):
    """Features at date t must be identical whether or not targets after t-H are known."""
    H = 28
    sales = dataset.sales[dataset.sales.sku_id == "SKU001"].copy()
    t = sales.date.iloc[-60]
    full = build_frame(sales, None, dataset.skus, H)
    masked = sales.copy()
    masked.loc[masked.date > t - pd.Timedelta(days=H), "units_sold"] = -999  # poison
    masked_frame = build_frame(masked.assign(units_sold=masked.units_sold.where(masked.units_sold >= 0)),
                               None, dataset.skus, H)
    cols = [c for c in feature_columns(H) if c.startswith(("lag_", "roll_", "dow_mean"))]
    a = full[full.date == t][cols].reset_index(drop=True)
    b = masked_frame[masked_frame.date == t][cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_folds_are_contiguous_and_ordered():
    folds = make_folds(pd.Timestamp("2026-09-30"), 28, 3)
    assert [f.index for f in folds] == [0, 1, 2]
    assert folds[-1].test_end == pd.Timestamp("2026-09-30")
    assert all(a.test_end == b.cutoff for a, b in itertools.pairwise(folds))


def test_conformal_achieves_nominal_coverage_on_exchangeable_data():
    rng = np.random.default_rng(0)
    n = 4000
    oof = pd.DataFrame({"store_id": "S01", "sku_id": "SKU001", "h": rng.integers(1, 29, n),
                        "yhat": 50.0, "stockout": False})
    oof["y"] = oof.yhat + rng.normal(0, 5, n)
    cal = ConformalCalibrator(alpha=0.2).fit(oof.iloc[:2000], pd.Series({("S01", "SKU001"): 5.0}))
    test = cal.apply(oof.iloc[2000:], oof.iloc[2000:]["h"])
    cov = ((test.y >= test.lo) & (test.y <= test.hi)).mean()
    assert 0.77 <= cov <= 0.84


def test_reconciliation_is_coherent_and_bottom_up_is_exact():
    bottom = [("S01", "A"), ("S01", "B"), ("S02", "A")]
    S, labels = summing_matrix(bottom)
    assert labels[0] == "total" and S.shape == (6, 3)
    rng = np.random.default_rng(1)
    base = rng.uniform(10, 20, (6, 5))  # incoherent on purpose
    for method in ("ols", "wls_struct", "bottom_up"):
        rec = reconcile(base, S, method)
        np.testing.assert_allclose(rec[0], rec[3:].sum(axis=0))       # total = sum(bottom)
        np.testing.assert_allclose(rec[1], rec[3] + rec[4])            # store S01 = its SKUs
    np.testing.assert_allclose(reconcile(base, S, "bottom_up")[3:], base[3:])


def test_tsb_decays_for_obsolete_items():
    alive = np.array([0, 3, 0, 0, 2, 0, 4] * 10, dtype=float)
    dead = np.concatenate([alive, np.zeros(60)])
    assert tsb_forecast(dead) < tsb_forecast(alive) * 0.5
