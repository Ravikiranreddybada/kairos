"""Turn probabilistic forecasts into inventory decisions.

A forecast is only valuable when it changes a decision. This module converts
(forecast mean, forecast uncertainty, supplier lead-time uncertainty) into a
continuous-review (s, Q) policy:

    d      = mean daily demand over the lead time      (from the forecast)
    sigma_d = daily forecast error std                 (from conformal interval width)
    L, sigma_L = supplier lead time mean / std         (from dim_supplier)

    safety stock  SS  = z * sqrt(L * sigma_d^2 + d^2 * sigma_L^2)
    reorder point ROP = d * L + SS
    order qty     Q   = max(MOQ, EOQ, ROP + d * review_days - inventory_position)

The combined-variance formula is the important part: most implementations
ignore lead-time variability, which under-stocks exactly the unreliable
suppliers that need buffer most.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from scipy.stats import norm


@dataclass(frozen=True)
class PolicyInput:
    store_id: str
    sku_id: str
    daily_mean: float
    daily_sigma: float
    lead_time_mean: float
    lead_time_std: float
    on_hand: float
    on_order: float
    unit_cost: float
    holding_rate_annual: float = 0.25
    order_cost: float = 500.0
    moq: float = 0.0
    service_level: float = 0.95
    review_days: float = 7.0


@dataclass(frozen=True)
class PolicyDecision:
    store_id: str
    sku_id: str
    service_level: float
    safety_stock: float
    reorder_point: float
    inventory_position: float
    days_of_cover: float | None  # None = no forecast demand (JSON has no inf)
    stockout_probability: float
    should_order: bool
    order_qty: float
    eoq: float
    annual_holding_cost_of_ss: float
    rationale: str

    def to_dict(self) -> dict[str, object]:
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def sigma_from_interval(lo: float, hi: float, alpha: float) -> float:
    """Back out a Gaussian-equivalent std from a (1-alpha) interval."""
    z = norm.ppf(1 - alpha / 2)
    return max((hi - lo) / (2 * z), 1e-6)


def decide(p: PolicyInput) -> PolicyDecision:
    if not 0.5 <= p.service_level < 1:
        raise ValueError("service_level must be in [0.5, 1)")
    z = float(norm.ppf(p.service_level))
    d, L = max(p.daily_mean, 0.0), max(p.lead_time_mean, 0.0)
    lt_var = L * p.daily_sigma**2 + d**2 * p.lead_time_std**2
    ss = z * math.sqrt(lt_var)
    rop = d * L + ss
    ip = p.on_hand + p.on_order

    annual_demand = d * 365
    holding_unit = p.unit_cost * p.holding_rate_annual
    eoq = math.sqrt(2 * annual_demand * p.order_cost / holding_unit) if holding_unit > 0 and d > 0 else 0.0

    # P(lead-time demand > inventory position) under Normal approximation.
    sd = math.sqrt(lt_var) if lt_var > 0 else 1e-6
    p_stockout = float(1 - norm.cdf((ip - d * L) / sd)) if d > 0 else 0.0

    should_order = d > 0 and ip <= rop  # never order an item nobody is forecast to buy
    qty = 0.0
    if should_order:
        target = rop + d * p.review_days
        qty = max(p.moq, eoq, target - ip)
        qty = float(math.ceil(qty))

    cover = p.on_hand / d if d > 0 else None
    reason = (
        f"ROP {rop:.0f} = {d:.1f}/day x {L:.1f}d lead time + SS {ss:.0f} "
        f"(z={z:.2f} for {p.service_level:.0%} CSL; lead-time std {p.lead_time_std:.1f}d "
        f"contributes {100 * (d**2 * p.lead_time_std**2) / lt_var if lt_var else 0:.0f}% of variance). "
        f"Position {ip:.0f} {'<=' if should_order else '>'} ROP"
        + (f" -> order {qty:.0f} (max of MOQ {p.moq:.0f}, EOQ {eoq:.0f}, gap-to-target)." if should_order else
           " -> no order needed.")
    )
    return PolicyDecision(
        store_id=p.store_id, sku_id=p.sku_id, service_level=p.service_level,
        safety_stock=ss, reorder_point=rop, inventory_position=ip, days_of_cover=cover,
        stockout_probability=p_stockout, should_order=should_order, order_qty=qty, eoq=eoq,
        annual_holding_cost_of_ss=ss * holding_unit, rationale=reason,
    )


def service_level_tradeoff(p: PolicyInput, levels: tuple[float, ...] = (0.9, 0.95, 0.98, 0.99)) -> list[dict[str, float]]:
    """Cost of each extra 'nine' of service – the curve planners actually negotiate on."""
    rows = []
    for sl in levels:
        dec = decide(PolicyInput(**{**asdict(p), "service_level": sl}))
        rows.append({"service_level": sl, "safety_stock": round(dec.safety_stock, 1),
                     "annual_holding_cost_of_ss": round(dec.annual_holding_cost_of_ss, 0)})
    return rows
