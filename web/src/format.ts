const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export const units = (n: number) => nf.format(n);
export const whole = (n: number) => nf0.format(n);
export const pct = (p: number, digits = 0) => `${(p * 100).toFixed(digits)}%`;
export const signedPct = (n: number) => `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
export const money = (n: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
export const ms = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(2)} s` : `${Math.round(n)} ms`);

export const reqNo = (n: number) => String(n).padStart(4, "0");

export function stampDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase();
}

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

/** Champion run ids look like 20261018T054200764610Z. */
export function runLabel(runId: string): string {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})/.exec(runId);
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]} UTC` : runId;
}

export const toolLabel: Record<string, string> = {
  get_forecast: "Demand forecast",
  inventory_policy: "Reorder policy",
  what_if_promo: "Promotion what-if",
  explain_forecast: "Forecast drivers",
  reorder_worklist: "Reorder worklist",
  detect_anomalies: "Demand anomalies",
  run_sql: "Warehouse query",
  simulate_supply_risk: "Supply risk simulation",
  network_pooling: "DC pooling",
  model_health: "Model health",
  decision_history: "Decision history",
  browse_docs: "Policy documents",
  search_docs: "Policy search",
};

/** Store / SKU subject of a requisition, read from its tool inputs. */
export function subjectOf(calls: { input: Record<string, unknown> }[] | undefined): string | null {
  if (!calls?.length) return null;
  const store = calls.map((c) => c.input?.store_id).find(Boolean);
  const sku = calls.map((c) => c.input?.sku_id).find(Boolean);
  return [store, sku].filter(Boolean).join(" ") || null;
}
