"""Demand classification from data alone (Syntetos-Boylan-Croston 2005: ADI 1.32, CV² 0.49)."""

import numpy as np
import pandas as pd

from kairos.forecasting.segmentation import classify_demand, model_segment


def _series(units, sku="SKU001"):
    dates = pd.date_range("2026-01-01", periods=len(units), freq="D")
    return pd.DataFrame({"date": dates, "store_id": "S01", "sku_id": sku, "units_sold": units,
                         "stockout": False})


def test_four_textbook_patterns():
    n = 120
    smooth = _series(np.full(n, 10), "SKU001")
    erratic = _series(np.tile([1, 30], n // 2), "SKU002")               # every day, sizes vary a lot
    intermittent = _series(np.tile([0, 0, 5], n // 3), "SKU003")       # 1 in 3 days, same size
    lumpy = _series(np.tile([0, 0, 1, 0, 0, 40], n // 6), "SKU004")    # rare and variable
    got = classify_demand(pd.concat([smooth, erratic, intermittent, lumpy])).set_index("sku_id")["pattern"]
    assert got.to_dict() == {"SKU001": "smooth", "SKU002": "erratic", "SKU003": "intermittent",
                             "SKU004": "lumpy"}


def test_stockout_days_do_not_count_as_zero_demand():
    s = _series(np.tile([0, 0, 5], 40))
    s.loc[s.units_sold == 0, "stockout"] = True  # zeros were censored, not "no demand"
    assert classify_demand(s)["pattern"].iloc[0] == "smooth"


def test_model_segment_groups_patterns_for_selection():
    assert model_segment("smooth") == model_segment("erratic") == "regular"
    assert model_segment("intermittent") == model_segment("lumpy") == "intermittent"


def test_data_driven_segments_agree_with_generator_truth(dataset):
    seg = classify_demand(dataset.sales).merge(dataset.skus[["sku_id", "is_intermittent"]], on="sku_id")
    agree = (seg["pattern"].map(model_segment).eq("intermittent") == seg["is_intermittent"]).mean()
    assert agree >= 0.9
