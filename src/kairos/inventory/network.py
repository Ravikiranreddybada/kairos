"""Two-echelon network: how much buffer a distribution centre (DC) saves.

Store-direct supply: every store holds its own safety stock against the full
supplier lead time L. With a DC, stores only buffer the short DC -> store leg
``l``; the DC holds one *pooled* buffer against L. Pooling works because store
forecast errors partly cancel:

    store-direct  SS = sum_i z * sqrt(L * s_i^2 + d_i^2 * sL^2)
    DC (pooled)   SS = z * sqrt(L * s_pool^2 + D^2 * sL^2),   s_pool^2 = s' R s
    store leg     SS = sum_i z * sqrt(l * s_i^2)

``R`` is the correlation of de-seasonalised daily demand between stores,
measured from history (not assumed 0). With R = I the DC term reduces to the
square-root law; with R = 1 everywhere pooling saves nothing. Lead-time
variance does *not* pool – every unit waits for the same supplier – which is
why the D^2 * sL^2 term uses total demand D.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm


@dataclass(frozen=True)
class NodeDemand:
    store_id: str
    daily_mean: float
    daily_sigma: float


def demand_correlation(sales: pd.DataFrame, stores: list[str], window_days: int = 182) -> np.ndarray:
    """Correlation of daily demand across stores after removing each store's weekday profile.

    Stockout days are censored demand (ADR-0004) and are excluded pairwise.
    """
    recent = sales[sales["date"] > sales["date"].max() - pd.Timedelta(days=window_days)].copy()
    recent["units"] = recent["units_sold"].astype(float).where(~recent["stockout"].astype(bool))
    recent["resid"] = recent["units"] - recent.groupby(
        ["store_id", recent["date"].dt.dayofweek])["units"].transform("mean")
    wide = recent.pivot_table(index="date", columns="store_id", values="resid").reindex(columns=stores)
    corr = wide.corr(min_periods=30).to_numpy()
    corr = np.where(np.isfinite(corr), corr, 0.0)
    np.fill_diagonal(corr, 1.0)
    return np.clip(corr, -1.0, 1.0)


def pooling(nodes: list[NodeDemand], corr: np.ndarray, lead_time_mean: float, lead_time_std: float,
            service_level: float, dc_to_store_days: float, unit_cost: float, holding_rate_annual: float
            ) -> dict[str, object]:
    if not 0.5 <= service_level < 1:
        raise ValueError("service_level must be in [0.5, 1)")
    z = float(norm.ppf(service_level))
    L, sL, leg = lead_time_mean, lead_time_std, dc_to_store_days
    s = np.array([n.daily_sigma for n in nodes])
    d = np.array([n.daily_mean for n in nodes])
    D = float(d.sum())

    store_ss = z * np.sqrt(L * s**2 + d**2 * sL**2)
    pooled_var = float(s @ corr @ s)
    dc_ss = z * math.sqrt(max(L * pooled_var + D**2 * sL**2, 0.0))
    leg_ss = z * np.sqrt(leg * s**2)
    sqrt_law_dc = z * math.sqrt(L * float((s**2).sum()) + D**2 * sL**2)  # independent stores (R = I)

    direct_total, echelon_total = float(store_ss.sum()), dc_ss + float(leg_ss.sum())
    saved = direct_total - echelon_total
    # Store-leg buffer grows with sqrt(l): the DC pays off while l is below this.
    leg_unit = z * float(s.sum())
    break_even = ((direct_total - dc_ss) / leg_unit) ** 2 if leg_unit > 0 and direct_total > dc_ss else 0.0
    lt_share = D**2 * sL**2 / (L * pooled_var + D**2 * sL**2) if L * pooled_var + D**2 * sL**2 > 0 else 0.0
    verdict = (f"a DC saves {saved:.0f} units of safety stock" if saved > 0 else
               f"a DC adds {-saved:.0f} units: the {leg:g}-day DC-to-store leg needs more buffer than pooling saves")
    if lt_share > 0.5:
        verdict += (f"; supplier lead-time variability drives {100 * lt_share:.0f}% of the pooled buffer and does "
                    "not pool, so a more reliable supplier saves more than a DC")
    holding = unit_cost * holding_rate_annual
    off = corr[~np.eye(len(nodes), dtype=bool)]
    return {
        "service_level": service_level,
        "stores": [{"store_id": n.store_id, "daily_mean": round(n.daily_mean, 2),
                    "daily_sigma": round(n.daily_sigma, 2), "store_direct_ss": round(float(a), 1),
                    "store_leg_ss": round(float(b), 1)}
                   for n, a, b in zip(nodes, store_ss, leg_ss, strict=True)],
        "mean_demand_correlation": round(float(off.mean()), 3) if len(off) else None,
        "store_direct_total_ss": round(direct_total, 1),
        "dc_pooled_ss": round(dc_ss, 1),
        "dc_pooled_ss_if_independent": round(sqrt_law_dc, 1),
        "two_echelon_total_ss": round(echelon_total, 1),
        "units_saved": round(saved, 1),
        "pct_saved": round(100 * saved / direct_total, 1) if direct_total else 0.0,
        "annual_holding_cost_saved": round(saved * holding, 0),
        "break_even_dc_to_store_days": round(break_even, 2),
        "lead_time_variance_share": round(lt_share, 3),
        "verdict": verdict,
        "lead_time_days": L, "dc_to_store_days": leg,
    }
