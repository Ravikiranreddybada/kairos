import type { ReactNode } from "react";
import { money, pct, signedPct, units, whole } from "../../format";
import type {
  Anomalies,
  Explain,
  Forecast,
  Health,
  Network,
  Policy,
  Proposals,
  Stress,
  WhatIf,
  Worklist,
} from "../../types";
import { ForecastFan } from "./ForecastFan";

// --------------------------------------------------------------- pieces

function Field({ label, value, big = false }: { label: string; value: ReactNode; big?: boolean }) {
  return (
    <div className="min-w-0 border-t border-canary-2 pt-1">
      <div className="text-[12px] text-[var(--on-canary-2)]">{label}</div>
      <div className={`num truncate text-ink ${big ? "text-[22px] leading-7" : "text-[15px]"}`}>{value}</div>
    </div>
  );
}

function Fields({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">{children}</div>;
}

/** An inline quantity bar: no track behind it, length is the value. */
function Bar({ value, max, tone = "ink" }: { value: number; max: number; tone?: "ink" | "errata" }) {
  const w = max > 0 ? Math.max(2, (Math.abs(value) / max) * 100) : 0;
  return <span aria-hidden className={`block h-[6px] ${tone === "errata" ? "bg-errata" : "bg-ink"}`} style={{ width: `${w}%` }} />;
}

function Table({ head, rows, align }: { head: string[]; rows: ReactNode[][]; align?: ("l" | "r")[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            {head.map((h, i) => (
              <th
                key={h}
                scope="col"
                className={`border-b border-rule-strong pb-1 font-medium text-[var(--on-canary-2)] ${align?.[i] === "r" ? "text-right" : "text-left"}`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j} className={`border-b border-canary-2 py-1 pr-2 last:pr-0 ${align?.[j] === "r" ? "num text-right text-ink" : "text-type"}`}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const Note = ({ children }: { children: ReactNode }) => <p className="mt-3 text-[13px] leading-5 text-type">{children}</p>;

// --------------------------------------------------------------- views

function PolicyView({ p }: { p: Policy }) {
  const d = p.decision;
  const maxSs = Math.max(...p.tradeoff.map((t) => t.safety_stock));
  return (
    <div>
      <Fields>
        <Field big label={d.should_order ? "Order now, units" : "No order needed"} value={d.should_order ? whole(d.order_qty) : "0"} />
        <Field big label="Stockout risk" value={pct(d.stockout_probability)} />
        <Field label="Service level" value={pct(d.service_level)} />
        <Field label="Reorder point" value={units(d.reorder_point)} />
        <Field label="Inventory position" value={units(d.inventory_position)} />
        <Field label="Safety stock" value={units(d.safety_stock)} />
        <Field label="Days of cover" value={units(d.days_of_cover)} />
        <Field label="EOQ" value={units(d.eoq)} />
        <Field label="Lead time" value={`${units(p.inputs.lead_time_mean)} d ± ${units(p.inputs.lead_time_std)}`} />
      </Fields>
      <Note>{d.rationale}</Note>
      <h4 className="mt-4 mb-1 text-[13px] font-semibold text-type">Cost of a higher service level</h4>
      <Table
        head={["Service level", "Safety stock", "", "Holding cost / yr"]}
        align={["l", "r", "l", "r"]}
        rows={p.tradeoff.map((t) => [
          <span className={t.service_level === d.service_level ? "font-semibold text-ink" : undefined}>
            {pct(t.service_level)}
            {t.service_level === d.service_level ? " (this answer)" : ""}
          </span>,
          units(t.safety_stock),
          <span className="block w-20">
            <Bar value={t.safety_stock} max={maxSs} />
          </span>,
          money(t.annual_holding_cost_of_ss),
        ])}
      />
    </div>
  );
}

function WorklistView({ w }: { w: Worklist }) {
  return (
    <div>
      <p className="mb-2 text-[13px] text-type">
        <span className="num text-ink">{w.to_order}</span> of <span className="num text-ink">{w.skus_checked}</span> SKUs at{" "}
        {w.store_id} need an order at {pct(w.service_level)} service.
      </p>
      <Table
        head={["SKU", "Stockout risk", "", "Order", "Position", "ROP"]}
        align={["l", "r", "l", "r", "r", "r"]}
        rows={w.items.map((i) => [
          <span className="num">{i.sku_id}</span>,
          pct(i.stockout_probability),
          <span className="block w-14">
            <Bar value={i.stockout_probability} max={1} tone={i.stockout_probability >= 0.5 ? "errata" : "ink"} />
          </span>,
          i.should_order ? whole(i.order_qty) : "-",
          units(i.inventory_position),
          units(i.reorder_point),
        ])}
      />
    </div>
  );
}

function StressView({ s }: { s: Stress }) {
  const rows: [string, (x: Stress["baseline"]) => string][] = [
    ["Chance of a stockout day", (x) => pct(x.prob_stockout_in_horizon)],
    ["Expected stockout days", (x) => units(x.expected_stockout_days)],
    ["Fill rate", (x) => pct(x.fill_rate, 1)],
    ["Expected lost units", (x) => units(x.expected_lost_units)],
    ["Ending stock (median)", (x) => units(x.ending_on_hand_p50)],
  ];
  const scen = [
    s.scenario.lead_time_delay_days ? `supplier ${s.scenario.lead_time_delay_days} days late` : null,
    s.scenario.demand_shock_pct ? `demand ${signedPct(s.scenario.demand_shock_pct)}` : null,
  ].filter(Boolean);
  return (
    <div>
      <Table
        head={["Next " + s.baseline.horizon_days + " days", "As is", scen.length ? "Scenario" : "Scenario (none)"]}
        align={["l", "r", "r"]}
        rows={rows.map(([label, f]) => [label, f(s.baseline), f(s.disrupted as Stress["baseline"])])}
      />
      <Fields>
        <Field big label="Order now, units" value={whole(s.recommended_order_now)} />
        <Field label="Risk change" value={`${s.stockout_risk_change_pts > 0 ? "+" : ""}${units(s.stockout_risk_change_pts)} pts`} />
        <Field label="Simulated ROP" value={units(s.distribution_free_reorder_point)} />
      </Fields>
      <Note>
        {scen.length ? `Scenario: ${scen.join(", ")}. ` : ""}
        {s.method}.
      </Note>
    </div>
  );
}

function NetworkView({ n }: { n: Network }) {
  return (
    <div>
      <Table
        head={["Store", "Daily mean", "Direct SS", "Leg SS"]}
        align={["l", "r", "r", "r"]}
        rows={n.stores.map((s) => [<span className="num">{s.store_id}</span>, units(s.daily_mean), units(s.store_direct_ss), units(s.store_leg_ss)])}
      />
      <Fields>
        <Field label="Direct total SS" value={units(n.store_direct_total_ss)} />
        <Field label="With a DC" value={units(n.two_echelon_total_ss)} />
        <Field label="Saved / yr" value={money(n.annual_holding_cost_saved)} />
      </Fields>
      <Note>{n.verdict}</Note>
    </div>
  );
}

function WhatIfView({ w }: { w: WhatIf }) {
  const max = Math.max(w.baseline_units, w.promo_units);
  return (
    <div>
      <div className="grid gap-2 text-[13px]">
        {[
          ["Without promotion", w.baseline_units],
          ["With 15% promotion", w.promo_units],
        ].map(([label, v]) => (
          <div key={label as string} className="grid grid-cols-[132px_minmax(0,1fr)_64px] items-center gap-3">
            <span className="text-type">{label}</span>
            <Bar value={v as number} max={max} />
            <span className="num text-right text-ink">{units(v as number)}</span>
          </div>
        ))}
      </div>
      <Fields>
        <Field label="Uplift" value={signedPct(w.uplift_pct)} />
        <Field label="Post-promo dip" value={units(w.post_promo_dip_units)} />
        <Field label="Net extra units" value={units(w.net_incremental_units)} />
      </Fields>
      <Note>
        {w.days}-day promotion from <span className="num">{w.start_date}</span>.
      </Note>
    </div>
  );
}

function ExplainView({ e }: { e: Explain }) {
  const max = Math.max(...e.drivers.map((d) => Math.abs(d.effect_pct)), 1);
  return (
    <div>
      <p className="mb-2 text-[13px] text-type">
        From a baseline of <span className="num text-ink">{units(e.baseline_units_per_day)}</span> units a day to{" "}
        <span className="num text-ink">{units(e.model_units_per_day)}</span> forecast.
      </p>
      <ul className="grid gap-1.5">
        {e.drivers.map((d) => (
          <li key={d.driver} className="grid grid-cols-[minmax(0,1fr)_120px_60px] items-center gap-3 text-[13px]">
            <span className="text-type">{d.driver}</span>
            <span className={`flex ${d.effect_pct < 0 ? "justify-end" : ""}`}>
              <span aria-hidden className="block h-[6px] bg-ink" style={{ width: `${Math.max(2, (Math.abs(d.effect_pct) / max) * 100)}%` }} />
            </span>
            <span className="num text-right text-ink">{signedPct(d.effect_pct)}</span>
          </li>
        ))}
      </ul>
      {e.note && <Note>{e.note}</Note>}
    </div>
  );
}

function HealthView({ h }: { h: Health }) {
  return (
    <div>
      <Fields>
        <Field big label="Status" value={h.status} />
        <Field label="Series drifting" value={`${h.series_drifting} of ${h.series_checked}`} />
        <Field label="Champion age" value={`${units(h.champion_age_days)} d`} />
        <Field label="Backtest WAPE" value={pct(h.backtest_wape, 1)} />
        <Field label="Interval coverage" value={pct(h.backtest_coverage, 1)} />
        <Field label="Level shifts" value={h.series_level_shifted} />
      </Fields>
      {h.worst.length > 0 && (
        <>
          <h4 className="mt-4 mb-1 text-[13px] font-semibold text-type">Most drifted series</h4>
          <Table
            head={["Series", "PSI", "Level shift"]}
            align={["l", "r", "r"]}
            rows={h.worst.map((w) => [<span className="num">{`${w.store_id} ${w.sku_id}`}</span>, w.psi.toFixed(3), signedPct(w.level_shift_pct)])}
          />
        </>
      )}
      {h.recommendation && <Note>{h.recommendation}</Note>}
    </div>
  );
}

function AnomalyView({ a }: { a: Anomalies }) {
  if (!a.count) return <p className="text-[13px] text-type">No anomalies above the threshold.</p>;
  return (
    <ul className="grid gap-2">
      {a.anomalies.map((x) => (
        <li key={`${x.date}${x.sku_id}${x.store_id}`} className="border-t border-canary-2 pt-1.5 text-[13px]">
          <span className="num text-ink">{x.date}</span> <span className="num text-[var(--on-canary-2)]">{`${x.store_id} ${x.sku_id}`}</span>
          <span className="num float-right text-ink">score {x.score.toFixed(1)}</span>
          <span className="block text-type">{x.explanation}</span>
        </li>
      ))}
    </ul>
  );
}

function ProposalsView({ p }: { p: Proposals }) {
  if (!p.count) return <p className="text-[13px] text-type">No proposals in the ledger for this filter yet.</p>;
  return (
    <Table
      head={["Proposal", "Series", "Status", "Rec. qty", "Final"]}
      align={["l", "l", "l", "r", "r"]}
      rows={p.items.map((i) => [
        <span className="num">{i.id.slice(0, 8)}</span>,
        <span className="num">{`${i.store_id} ${i.sku_id}`}</span>,
        i.status,
        whole(i.recommended_qty),
        i.final_qty == null ? "-" : whole(i.final_qty),
      ])}
    />
  );
}

function FromInputs({ name, input, citations }: { name: string; input?: Record<string, unknown>; citations?: string[] }) {
  if (name === "run_sql") {
    return (
      <div>
        <p className="mb-1 text-[13px] text-type">Read-only query, checked by the SQL guard before it ran:</p>
        <pre className="num overflow-x-auto whitespace-pre-wrap border border-canary-2 bg-[var(--ink-wash)] p-2 text-[12px] text-ink">
          {String(input?.query ?? "")}
        </pre>
      </div>
    );
  }
  const q = input?.query ?? input?.node_id;
  return (
    <div className="text-[13px] text-type">
      {q ? (
        <p>
          Looked up <span className="num text-ink">{String(q)}</span> in the policy documents.
        </p>
      ) : (
        <p>Read the document outline.</p>
      )}
      {citations && citations.length > 0 && (
        <p className="mt-1">
          Sections cited in the answer: <span className="num text-ink">{citations.join(", ")}</span>
        </p>
      )}
    </div>
  );
}

export function EvidenceView({ name, data, input, citations }: { name: string; data: unknown; input?: Record<string, unknown>; citations?: string[] }) {
  if (data == null) return <FromInputs name={name} input={input} citations={citations} />;
  switch (name) {
    case "get_forecast":
      return <ForecastFan f={data as Forecast} />;
    case "inventory_policy":
      return <PolicyView p={data as Policy} />;
    case "reorder_worklist":
      return <WorklistView w={data as Worklist} />;
    case "simulate_supply_risk":
      return <StressView s={data as Stress} />;
    case "network_pooling":
      return <NetworkView n={data as Network} />;
    case "what_if_promo":
      return <WhatIfView w={data as WhatIf} />;
    case "explain_forecast":
      return <ExplainView e={data as Explain} />;
    case "model_health":
      return <HealthView h={data as Health} />;
    case "detect_anomalies":
      return <AnomalyView a={data as Anomalies} />;
    case "decision_history":
      return <ProposalsView p={data as Proposals} />;
    default:
      return <pre className="num overflow-x-auto text-[11.5px]">{JSON.stringify(data, null, 2)}</pre>;
  }
}
