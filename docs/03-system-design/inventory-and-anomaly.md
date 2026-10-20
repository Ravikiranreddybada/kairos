# Inventory optimisation and anomaly detection

Code: `src/kairos/inventory/policy.py`, `src/kairos/anomaly/detector.py`.

## Inventory policy: continuous review (s, Q)

Inputs per store × SKU:

| Symbol | Source |
|---|---|
| d – mean daily demand over lead time | `fact_forecast.yhat` over the first L days |
| σ_d – daily forecast error std | back-solved from the conformal interval: (hi − lo) / (2·z_{1−α/2}) |
| L, σ_L – lead time mean / std | `dim_supplier` |
| on hand, on order | `fact_inventory` |
| unit cost, holding rate, MOQ | `dim_sku`, `dim_supplier` |
| CSL – cycle service level | request, planner preference, or policy default |

```
z   = Φ⁻¹(CSL)
SS  = z · sqrt(L·σ_d² + d²·σ_L²)        # demand AND lead-time uncertainty
ROP = d·L + SS
IP  = on_hand + on_order
order if IP ≤ ROP:  Q = max(MOQ, EOQ, ROP + d·review_days − IP)
EOQ = sqrt(2·D·K / h),  D = 365·d, h = unit_cost · holding_rate
P(stockout in lead time) ≈ 1 − Φ((IP − d·L) / sqrt(L·σ_d² + d²·σ_L²))
```

**Why the combined formula matters.** For SKU002 at S01 (d≈40/day, L=7d,
σ_L=2d), lead-time variance is ~86% of total variance. A demand-only formula
would cut safety stock by more than half – and stock out on exactly the
unreliable suppliers. Policy v3.2 forbids the demand-only formula for
suppliers below 90% on-time, so the code and the document agree.

**Service-level curve.** Each answer includes the safety stock and annual
holding cost at 90/95/98/99%. Moving from 95% → 99% costs +41% safety stock
for that SKU. That curve is what planners and finance actually negotiate on;
showing it turns "the model says" into a business choice.

**Every decision carries a rationale string** – e.g. *"ROP 422 = 40.0/day ×
7.0d lead time + SS 142 (z=1.64 for 95% CSL; lead-time std 2.0d contributes
86% of variance). Position 180 ≤ ROP → order 698 (max of MOQ 100, EOQ 698,
gap-to-target)."*

Known simplifications (documented, on roadmap): Gaussian lead-time demand;
cycle service level rather than fill rate; single echelon.

## Anomaly detection

```
level_t    = rolling median (29d, centred)
baseline_t = level_t × weekday factor (median ratio by weekday)
score_t    = (y_t − baseline_t) / max(1.4826·MAD(residuals), 1)
flag if |score| ≥ threshold and baseline ≥ 2 units/day
explained_by ∈ {stockout, promotion, festival, ""}
```

Design choices:

* **Robust statistics, not IsolationForest/autoencoders.** Medians and MAD
  are not pulled by the outliers they are trying to find; no training, no
  drift, and every flag has a human-readable reason.
* **Attribution instead of suppression.** Promo/festival/stockout spikes are
  returned as *explained*, not hidden – useful context, but they do not
  page anyone. Without attribution, ~70% of flags at threshold 4 are
  promotions, and planners would learn to ignore the alerts.
* **Sparse-series floor.** Baseline < 2 units/day are skipped; a jump from 0
  to 3 units is noise, not an anomaly.

Precision / recall vs injected ground truth (unexplained flags only):

| Threshold | Precision | Recall | F1 | Flags |
|---|---|---|---|---|
| 4.0 | 0.45 | 0.62 | 0.53 | 106 |
| **5.0 (default)** | **0.77** | **0.62** | **0.69** | 62 |
| 6.0 | 0.94 | 0.57 | 0.71 | 47 |

Default 5.0: the escalation SOP sends planners to verify every flag, so a
false positive costs a planner's time; 5.0 keeps recall while cutting false
alarms by 40% vs 4.0. Recall is capped near 0.62 because ~1/3 of injected
anomalies are "drops to zero" on low-volume series, which are
indistinguishable from intermittent demand – a stated limitation.
