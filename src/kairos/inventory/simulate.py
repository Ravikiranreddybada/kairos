"""Monte-Carlo supply twin: stress-test a reorder policy before reality does.

The closed-form policy (``policy.decide``) answers "what is the reorder point?"
under a Normal approximation. Planners also ask questions it cannot answer:

* "What happens if the supplier is 7 days late?"
* "What if demand runs 30% hot for a month?"
* "How many units do we actually lose, not just *whether* we stock out?"

This module simulates thousands of demand and lead-time paths through the same
(s, S) policy and reports the *distribution* of outcomes:

    demand_t   ~ Poisson(Gamma(mean_t, var_t))      over-dispersed count demand,
                                                    mean/var from the conformal forecast
    lead time  ~ Gamma(L + delay, sigma_L)          rounded to whole days, >= 1
    policy     : continuous review; when position <= s order up to S (>= MOQ)
    retail     : unmet demand is lost (no backorders)

It also gives a **distribution-free reorder point**: the service-level quantile
of simulated lead-time demand. That replaces the Gaussian ``d*L + z*sigma`` for
skewed, intermittent or disrupted demand – the newsvendor answer on the full
predictive distribution (roadmap item 3).

Everything is seeded, so the same question gives the same answer (cacheable,
testable, and auditable).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SimInput:
    daily_mean: np.ndarray  # forecast mean per day, length H
    daily_sigma: np.ndarray  # forecast std per day, length H
    on_hand: float
    on_order: float
    lead_time_mean: float
    lead_time_std: float
    reorder_point: float
    order_up_to: float
    moq: float = 0.0
    service_level: float = 0.95
    review_days: float = 7.0
    demand_shock_pct: float = 0.0
    lead_time_delay_days: float = 0.0
    n_paths: int = 2000
    seed: int = 0


def _extend(x: np.ndarray, n: int) -> np.ndarray:
    """Extend a daily profile past the forecast horizon by repeating its last week."""
    if len(x) >= n:
        return x[:n]
    tail = x[-7:] if len(x) >= 7 else x
    reps = math.ceil((n - len(x)) / len(tail))
    return np.concatenate([x, np.tile(tail, reps)])[:n]


def sample_demand(rng: np.random.Generator, mean: np.ndarray, sigma: np.ndarray, n: int) -> np.ndarray:
    """Gamma-Poisson (negative-binomial) daily demand with the forecast's mean and variance."""
    m = np.clip(np.asarray(mean, float), 0.0, None)
    extra = np.maximum(np.asarray(sigma, float) ** 2 - m, 1e-6)  # variance beyond Poisson
    pos = m > 0
    shape = np.where(pos, m**2 / extra, 1.0)
    scale = np.where(pos, extra / np.where(pos, m, 1.0), 0.0)
    lam = rng.gamma(shape, scale, size=(n, len(m)))
    return rng.poisson(lam).astype(float)


def sample_lead_times(rng: np.random.Generator, mean: float, std: float, size: int | tuple[int, ...]
                      ) -> np.ndarray:
    mean = max(mean, 1.0)
    std = max(std, 1e-3)
    shape, scale = (mean / std) ** 2, std**2 / mean
    return np.maximum(1, np.rint(rng.gamma(shape, scale, size=size))).astype(int)


@dataclass(frozen=True)
class SimResult:
    prob_stockout_in_horizon: float  # P(at least one day with lost sales in the horizon)
    expected_stockout_days: float
    fill_rate: float  # served units / demanded units
    expected_lost_units: float
    lost_units_p90: float
    ending_on_hand_p10: float
    ending_on_hand_p50: float
    ending_on_hand_p90: float
    expected_orders: float
    first_stockout_day_median: float | None
    quantile_reorder_point: float  # service-level quantile of simulated lead-time demand
    horizon_days: int
    n_paths: int

    def to_dict(self) -> dict[str, float | int | None]:
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


def simulate(p: SimInput) -> SimResult:
    if not 0.5 <= p.service_level < 1:
        raise ValueError("service_level must be in [0.5, 1)")
    rng = np.random.default_rng(p.seed)
    n, H = p.n_paths, len(p.daily_mean)
    shock = 1 + p.demand_shock_pct / 100
    lt_mean = p.lead_time_mean + p.lead_time_delay_days
    max_lt = math.ceil(lt_mean + 6 * p.lead_time_std) + 2

    mean = _extend(np.asarray(p.daily_mean, float) * shock, H + max_lt)
    sigma = _extend(np.asarray(p.daily_sigma, float) * shock, H + max_lt)
    demand = sample_demand(rng, mean, sigma, n)

    arrivals = np.zeros((n, H + max_lt + 1))
    rows = np.arange(n)
    if p.on_order > 0:  # an open order arrives somewhere inside its (possibly delayed) lead time
        first = rng.integers(1, max(2, math.ceil(lt_mean) + 1), size=n)
        arrivals[rows, first] += p.on_order
    on_hand = np.full(n, float(p.on_hand))
    pipeline = np.full(n, float(p.on_order))
    lost = np.zeros((n, H))
    orders = np.zeros(n)

    for t in range(H):
        on_hand += arrivals[:, t]
        pipeline -= arrivals[:, t]
        d = demand[:, t]
        served = np.minimum(on_hand, d)
        lost[:, t] = d - served
        on_hand -= served
        position = on_hand + pipeline
        need = position <= p.reorder_point
        if need.any():
            qty = np.where(need, np.maximum(np.ceil(p.order_up_to - position), p.moq), 0.0)
            lt = sample_lead_times(rng, lt_mean, p.lead_time_std, n)
            np.add.at(arrivals, (rows[need], t + lt[need]), qty[need])
            pipeline += qty
            orders += need

    demand_h = demand[:, :H]
    stockout_days = (lost > 0).sum(axis=1)
    any_out = stockout_days > 0
    first_out = np.argmax(lost > 0, axis=1)[any_out] + 1

    # Distribution-free ROP: quantile of demand over a sampled (delayed) lead time.
    lt = sample_lead_times(rng, lt_mean, p.lead_time_std, n)
    cum = np.cumsum(demand, axis=1)
    ltd = cum[rows, np.minimum(lt, cum.shape[1]) - 1]
    total_demand = float(demand_h.sum())

    return SimResult(
        prob_stockout_in_horizon=float(any_out.mean()),
        expected_stockout_days=float(stockout_days.mean()),
        fill_rate=float(1 - lost.sum() / total_demand) if total_demand > 0 else 1.0,
        expected_lost_units=float(lost.sum(axis=1).mean()),
        lost_units_p90=float(np.percentile(lost.sum(axis=1), 90)),
        ending_on_hand_p10=float(np.percentile(on_hand, 10)),
        ending_on_hand_p50=float(np.percentile(on_hand, 50)),
        ending_on_hand_p90=float(np.percentile(on_hand, 90)),
        expected_orders=float(orders.mean()),
        first_stockout_day_median=float(np.median(first_out)) if len(first_out) else None,
        quantile_reorder_point=float(np.quantile(ltd, p.service_level)),
        horizon_days=H,
        n_paths=n,
    )
