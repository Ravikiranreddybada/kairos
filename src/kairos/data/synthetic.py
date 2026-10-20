"""Deterministic synthetic retail supply-chain data.

Why synthetic: real client data is confidential, but the generator encodes
the *pathologies* real data has, so every downstream component is tested
against them:

* multiplicative weekly + yearly seasonality and per-series trend
* promotions with uplift and a post-promo dip (pull-forward effect)
* festival spikes (Diwali-like window, moves every year)
* **censored demand**: sales = min(demand, stock). Stockout days hide true
  demand; naive models learn the stockout as "low demand" (see ADR-0004)
* intermittent (slow-moving) SKUs where most days are zero
* injected point anomalies with ground-truth labels for detector eval
* price changes and supplier lead-time variability for inventory policy
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

CATEGORIES = ("beverages", "snacks", "personal_care", "household")
REGIONS = ("north", "south", "east", "west")

# Approximate festival peaks (Diwali) – moves each year, which defeats a pure
# 365-day seasonal lag and rewards explicit calendar features.
FESTIVAL_DATES = {
    2023: "2023-11-12",
    2024: "2024-11-01",
    2025: "2025-10-21",
    2026: "2026-11-08",
    2027: "2027-10-29",
}


@dataclass(frozen=True)
class SyntheticDataset:
    stores: pd.DataFrame
    skus: pd.DataFrame
    suppliers: pd.DataFrame
    sales: pd.DataFrame
    inventory: pd.DataFrame
    anomalies: pd.DataFrame  # ground truth for evaluating the detector


def festival_flag(dates: pd.DatetimeIndex, window: int = 5) -> np.ndarray:
    flag = np.zeros(len(dates), dtype=float)
    for d in FESTIVAL_DATES.values():
        center = pd.Timestamp(d)
        dist = np.abs((dates - center).days.to_numpy())
        flag = np.maximum(flag, np.clip(1 - dist / window, 0, 1))
    return flag


def generate(
    n_stores: int = 4,
    n_skus: int = 12,
    days: int = 730,
    end: str = "2026-09-30",
    seed: int = 7,
) -> SyntheticDataset:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=pd.Timestamp(end), periods=days, freq="D")
    t = np.arange(days)

    suppliers = pd.DataFrame(
        {
            "supplier_id": [f"SUP{i:02d}" for i in range(1, 5)],
            "name": ["Acme Foods", "Brightline Beverages", "CleanCo", "DailyNeeds Mfg"],
            "lead_time_mean_days": [5.0, 7.0, 10.0, 14.0],
            "lead_time_std_days": [1.0, 2.0, 3.0, 4.0],
            "moq_units": [50, 100, 40, 200],
            "on_time_rate": [0.97, 0.91, 0.88, 0.82],
        }
    )

    stores = pd.DataFrame(
        {
            "store_id": [f"S{i:02d}" for i in range(1, n_stores + 1)],
            "region": [REGIONS[i % len(REGIONS)] for i in range(n_stores)],
            "size_factor": rng.uniform(0.7, 1.5, n_stores).round(2),
        }
    )

    sku_rows = []
    for i in range(n_skus):
        cat = CATEGORIES[i % len(CATEGORIES)]
        intermittent = i % 6 == 5  # every 6th SKU is slow-moving
        list_price = float(rng.uniform(20, 400))
        sku_rows.append(
            {
                "sku_id": f"SKU{i + 1:03d}",
                "category": cat,
                "supplier_id": suppliers.supplier_id.iloc[i % len(suppliers)],
                "base_price": round(list_price, 2),
                "unit_cost": round(list_price * rng.uniform(0.45, 0.7), 2),
                "holding_cost_rate_annual": 0.25,
                "base_demand": float(rng.uniform(0.3, 1.2) if intermittent else rng.uniform(8, 60)),
                "is_intermittent": intermittent,
            }
        )
    skus = pd.DataFrame(sku_rows)

    weekly_profile = {
        "beverages": [0.9, 0.85, 0.9, 1.0, 1.15, 1.3, 1.2],
        "snacks": [0.85, 0.85, 0.9, 1.0, 1.2, 1.35, 1.15],
        "personal_care": [1.0, 0.95, 0.95, 1.0, 1.05, 1.1, 1.0],
        "household": [0.95, 0.9, 0.95, 1.0, 1.05, 1.2, 1.1],
    }
    festival = festival_flag(dates)
    dow = dates.dayofweek.to_numpy()
    doy = dates.dayofyear.to_numpy()

    frames: list[pd.DataFrame] = []
    anomalies: list[dict[str, object]] = []
    on_hand_rows: list[dict[str, object]] = []

    for _, store in stores.iterrows():
        for _, sku in skus.iterrows():
            base = sku.base_demand * store.size_factor
            trend = 1 + rng.normal(0.0002, 0.0003) * t
            yearly = 1 + 0.18 * np.sin(2 * np.pi * (doy - 80) / 365.25) * (
                1.0 if sku.category == "beverages" else 0.4
            )
            weekly = np.array(weekly_profile[sku.category])[dow]
            fest = 1 + festival * (1.4 if sku.category in ("snacks", "household") else 0.6)

            # Promotions: ~6 per year, 3-7 days, 20-60% uplift and a 3-day dip after.
            promo = np.zeros(days)
            for start in rng.choice(days - 10, size=max(1, days // 60), replace=False):
                length = int(rng.integers(3, 8))
                promo[start : start + length] = 1
            uplift = 1 + promo * rng.uniform(0.2, 0.6)
            dip = np.ones(days)
            ends = np.where((promo[:-1] == 1) & (promo[1:] == 0))[0] + 1
            for e in ends:
                dip[e : e + 3] *= 0.8

            price = np.full(days, sku.base_price)
            price[promo == 1] *= 0.85
            change_day = int(rng.integers(days // 3, days - 60))
            price[change_day:] *= rng.uniform(1.03, 1.10)  # inflation step
            elasticity = rng.uniform(-1.4, -0.6)
            price_effect = (price / sku.base_price) ** elasticity

            lam = np.clip(base * trend * yearly * weekly * fest * uplift * dip * price_effect, 0.01, None)
            if sku.is_intermittent:
                demand = rng.poisson(lam).astype(float)
            else:
                # Negative binomial = over-dispersed Poisson (retail reality).
                r = 8.0
                demand = rng.negative_binomial(r, r / (r + lam)).astype(float)

            # Stockouts: a few multi-day windows where supply ran out.
            stock_cap = np.full(days, np.inf)
            for start in rng.choice(days - 5, size=int(rng.integers(1, 4)), replace=False):
                length = int(rng.integers(2, 6))
                stock_cap[start : start + length] = np.floor(lam[start : start + length] * 0.15)
            units = np.minimum(demand, stock_cap)
            stockout = (stock_cap < np.inf) & (demand > stock_cap)

            # Point anomalies (data-entry errors / one-off bulk buys), labelled.
            if not sku.is_intermittent:
                for idx in rng.choice(np.arange(30, days), size=2, replace=False):
                    factor = float(rng.choice([4.0, 6.0, 0.0]))
                    if stockout[idx]:
                        continue
                    units[idx] = round(lam[idx] * factor)
                    anomalies.append(
                        {"date": dates[idx], "store_id": store.store_id, "sku_id": sku.sku_id,
                         "kind": "spike" if factor > 1 else "drop"}
                    )

            frames.append(
                pd.DataFrame(
                    {
                        "date": dates,
                        "store_id": store.store_id,
                        "sku_id": sku.sku_id,
                        "units_sold": units.astype(int),
                        "price": price.round(2),
                        "on_promo": promo.astype(bool),
                        "stockout": stockout,
                    }
                )
            )
            on_hand_rows.append(
                {
                    "store_id": store.store_id,
                    "sku_id": sku.sku_id,
                    "as_of": dates[-1],
                    "on_hand_units": int(max(0, rng.normal(lam[-30:].mean() * 9, lam[-30:].mean() * 3))),
                    "on_order_units": int(rng.choice([0, 0, sku.base_demand * 7])),
                }
            )

    sales = pd.concat(frames, ignore_index=True)
    return SyntheticDataset(
        stores=stores,
        skus=skus,
        suppliers=suppliers,
        sales=sales,
        inventory=pd.DataFrame(on_hand_rows),
        anomalies=pd.DataFrame(anomalies, columns=["date", "store_id", "sku_id", "kind"]),
    )
