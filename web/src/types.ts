// Shapes of the Kairos /v1 API that the copilot surface reads.

export type GraphNode = "guard" | "route" | "cache" | "llm" | "tools" | "verify" | "finalize";

export interface NodeEvent {
  event: "node";
  node: GraphNode;
  tools?: string[];
}

export type AnswerStatus = "ok" | "cached" | "blocked" | "degraded" | "budget_exhausted";

export interface ToolCall {
  name: string;
  input: Record<string, unknown>;
  is_error: boolean;
  latency_ms: number;
}

export interface Grounding {
  score?: number;
  checked?: number;
  ungrounded?: string[];
  passed?: boolean;
}

export interface ChatResult {
  answer: string;
  status: AnswerStatus;
  tier: string;
  tool_calls: ToolCall[];
  citations: string[];
  grounding: Grounding;
  usage: { input_tokens?: number; output_tokens?: number; cache_read_tokens?: number; cache_write_tokens?: number };
  cost_usd: number;
  latency_ms: number;
  trace_id: string | null;
  data_version: string;
  extra?: { steps?: number; revisions?: number };
}

export type Phase = "draft" | "routing" | "done" | "error";

export interface Requisition {
  id: string;
  no: number;
  question: string;
  createdAt: string;
  phase: Phase;
  nodes: NodeEvent[];
  result?: ChatResult;
  error?: string;
}

// ------------------------------------------------------------ evidence

export interface ForecastDay {
  date: string;
  yhat: number;
  lo: number;
  hi: number;
}
export interface Forecast {
  store_id: string;
  sku_id: string;
  horizon_days: number;
  total_units: number;
  total_lo: number;
  total_hi: number;
  interval: string;
  model: string;
  run_id: string;
  daily: ForecastDay[];
}

export interface Policy {
  decision: {
    store_id: string;
    sku_id: string;
    service_level: number;
    safety_stock: number;
    reorder_point: number;
    inventory_position: number;
    days_of_cover: number;
    stockout_probability: number;
    should_order: boolean;
    order_qty: number;
    eoq: number;
    annual_holding_cost_of_ss: number;
    rationale: string;
  };
  tradeoff: { service_level: number; safety_stock: number; annual_holding_cost_of_ss: number }[];
  inputs: { daily_mean: number; daily_sigma: number; lead_time_mean: number; lead_time_std: number };
  run_id: string;
}

export interface Worklist {
  store_id: string;
  service_level: number;
  skus_checked: number;
  to_order: number;
  items: {
    sku_id: string;
    stockout_probability: number;
    should_order: boolean;
    order_qty: number;
    inventory_position: number;
    reorder_point: number;
    days_of_cover: number;
  }[];
}

export interface StressSide {
  prob_stockout_in_horizon: number;
  expected_stockout_days: number;
  fill_rate: number;
  expected_lost_units: number;
  ending_on_hand_p50: number;
  quantile_reorder_point: number;
}
export interface Stress {
  store_id: string;
  sku_id: string;
  scenario: { lead_time_delay_days: number; demand_shock_pct: number };
  policy: { reorder_point: number; inventory_position: number };
  baseline: StressSide & { n_paths: number; horizon_days: number };
  disrupted: StressSide;
  stockout_risk_change_pts: number;
  distribution_free_reorder_point: number;
  recommended_order_now: number;
  method: string;
}

export interface Network {
  sku_id: string;
  service_level: number;
  stores: { store_id: string; daily_mean: number; store_direct_ss: number; store_leg_ss: number }[];
  mean_demand_correlation: number;
  store_direct_total_ss: number;
  two_echelon_total_ss: number;
  units_saved: number;
  pct_saved: number;
  annual_holding_cost_saved: number;
  verdict: string;
}

export interface WhatIf {
  store_id: string;
  sku_id: string;
  start_date: string;
  days: number;
  baseline_units: number;
  promo_units: number;
  uplift_pct: number;
  post_promo_dip_units: number;
  net_incremental_units: number;
}

export interface Explain {
  store_id: string;
  sku_id: string;
  horizon_days: number;
  baseline_units_per_day: number;
  model_units_per_day: number;
  drivers: { driver: string; effect_pct: number }[];
  served_model: string;
  note: string | null;
}

export interface Health {
  status: string;
  series_checked: number;
  series_drifting: number;
  drifting_share: number;
  series_level_shifted: number;
  champion_age_days: number;
  backtest_wape: number;
  backtest_coverage: number;
  recommendation?: string;
  worst: { store_id: string; sku_id: string; psi: number; level_shift_pct: number; drifting: boolean }[];
}

export interface Anomalies {
  count: number;
  anomalies: { date: string; store_id: string; sku_id: string; units_sold: number; score: number; explanation: string }[];
}

export interface Proposals {
  count: number;
  items: { id: string; store_id: string; sku_id: string; status: string; recommended_qty: number; final_qty: number | null }[];
}

export interface ModelCard {
  run_id: string;
  gates?: { name: string; passed: boolean; detail: string }[];
}
