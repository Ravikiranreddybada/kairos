"""Demand-pattern classification from data (Syntetos, Boylan & Croston, 2005).

Model selection is done per segment, so the segment must come from the data
we would really have – not from a master-data flag or a generator label.
Two statistics per series, over observed (non-stockout) days:

* **ADI** – average inter-demand interval = observed days / days with demand
* **CV²** – squared coefficient of variation of the non-zero demand sizes

and the published cut-offs (ADI 1.32, CV² 0.49) give four patterns:

                 CV² < 0.49      CV² >= 0.49
    ADI < 1.32   smooth          erratic
    ADI >= 1.32  intermittent    lumpy

Smooth/erratic series suit ETS and GBMs; intermittent/lumpy series are where
Croston-type methods (TSB) win. Stockout days are excluded: a zero caused by
an empty shelf is censored demand, not "no demand" (ADR-0004).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ADI_CUTOFF = 1.32
CV2_CUTOFF = 0.49
KEYS = ["store_id", "sku_id"]


def _stats(units: np.ndarray) -> tuple[float, float]:
    nz = units[units > 0]
    if len(nz) == 0:
        return float("inf"), 0.0
    adi = len(units) / len(nz)
    mean = float(nz.mean())
    cv2 = float((nz.std() / mean) ** 2) if mean > 0 else 0.0
    return adi, cv2


def _pattern(adi: float, cv2: float) -> str:
    if adi < ADI_CUTOFF:
        return "smooth" if cv2 < CV2_CUTOFF else "erratic"
    return "intermittent" if cv2 < CV2_CUTOFF else "lumpy"


def classify_demand(sales: pd.DataFrame, window_days: int = 365) -> pd.DataFrame:
    """One row per series: store_id, sku_id, adi, cv2, pattern."""
    recent = sales[sales["date"] > sales["date"].max() - pd.Timedelta(days=window_days)]
    observed = recent[~recent["stockout"].astype(bool)]
    rows = []
    for (store, sku), g in observed.groupby(KEYS, sort=True):
        adi, cv2 = _stats(g["units_sold"].to_numpy(float))
        rows.append({"store_id": store, "sku_id": sku, "adi": round(adi, 3), "cv2": round(cv2, 3),
                     "pattern": _pattern(adi, cv2)})
    return pd.DataFrame(rows, columns=[*KEYS, "adi", "cv2", "pattern"])


def model_segment(pattern: str) -> str:
    """Collapse the four patterns into the two model-selection segments."""
    return "intermittent" if pattern in ("intermittent", "lumpy") else "regular"


def segment_map(sales: pd.DataFrame) -> dict[tuple[str, str], str]:
    seg = classify_demand(sales)
    return {(r.store_id, r.sku_id): model_segment(r.pattern) for r in seg.itertuples()}
