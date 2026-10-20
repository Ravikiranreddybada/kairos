# Data model and data flow

## Star schema

```mermaid
erDiagram
  dim_store ||--o{ fact_sales : has
  dim_sku ||--o{ fact_sales : has
  dim_supplier ||--o{ dim_sku : supplies
  dim_store ||--o{ fact_inventory : has
  dim_sku ||--o{ fact_inventory : has
  dim_store ||--o{ fact_forecast : has
  dim_sku ||--o{ fact_forecast : has
  dim_store { text store_id PK  text region  double size_factor }
  dim_sku { text sku_id PK  text category  text supplier_id FK  double base_price  double unit_cost  bool is_intermittent }
  dim_supplier { text supplier_id PK  double lead_time_mean_days  double lead_time_std_days  int moq_units  double on_time_rate }
  fact_sales { date date  text store_id  text sku_id  int units_sold  double price  bool on_promo  bool stockout }
  fact_inventory { text store_id  text sku_id  date as_of  int on_hand_units  int on_order_units }
  fact_forecast { date date  text store_id  text sku_id  double yhat  double lo  double hi  text model  text run_id }
```

Plus `fact_forecast_hierarchy(date, node, yhat, run_id)` with nodes `total`,
`store:<id>`, `<store>|<sku>`.

**Grain matters.** `fact_sales` is one row per day × store × SKU. Contracts
enforce uniqueness and no calendar gaps, because a missing day silently shifts
every lag feature by one.

## Flow

```mermaid
flowchart LR
  src[Source systems<br/>POS · ERP · supplier portal] -->|daily load| raw[(fact_sales<br/>fact_inventory)]
  raw --> dq{Data contracts}
  dq -- error --> stop[Block training<br/>alert]
  dq -- ok --> bt[Backtest candidates]
  bt --> sel[Select per segment]
  sel --> cal[Conformal calibration]
  cal --> fit[Refit on full history]
  fit --> rec[Reconcile hierarchy]
  rec --> gate{Promotion gates}
  gate -- fail --> keep[Keep champion<br/>store run for audit]
  gate -- pass --> pub[(fact_forecast<br/>atomic swap)]
  pub --> serve[ForecastService / API / tools]
  docs[Policy docs] --> chunk[Chunk + sanitise] --> idx[(Hybrid index)]
  idx --> serve
```

## Synthetic data: what each pathology tests

| Pathology in generator | Breaks naïve systems by… | Handled in |
|---|---|---|
| Weekly + yearly seasonality, trend | Moving averages lag | ETS, GBM calendar features |
| Moving festival (Diwali) | 365-day lag misaligns | `festival` feature |
| Promotions + post-promo dip | Over-forecast after promo | `on_promo`, `promo_ended_3d` |
| Price inflation step + elasticity | Level shift looks like trend | `price_ratio` |
| Negative-binomial noise | Gaussian assumptions | Tweedie objective, conformal |
| **Stockout censoring** | Learns empty shelf = low demand | Masking (ADR-0004) |
| Intermittent SKUs | MAPE undefined, ETS over-forecasts | Segment selection, TSB |
| Point anomalies (labelled) | Contaminate training, false alerts | Robust detector, eval vs truth |
| Supplier lead-time variance | Under-stocked unreliable suppliers | Combined-variance safety stock |

## Data versioning

Every training run records a SHA-256 fingerprint of the sales table, row
count and date range in `manifest.json`. Two runs with the same fingerprint
and code produce identical metrics (seeded). In production, swap the
fingerprint for a table snapshot id (Snowflake time travel / Delta version).
