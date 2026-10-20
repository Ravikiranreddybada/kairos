import { ms, runLabel, toolLabel } from "../format";
import type { Requisition } from "../types";
import { stampFor } from "./Stamp";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[132px_minmax(0,1fr)] items-baseline gap-3 border-b border-pink-2 py-1.5">
      <dt className="text-[12.5px] text-[var(--on-pink-2)]">{label}</dt>
      <dd className="num min-w-0 break-words text-[13px] text-ink">{children}</dd>
    </div>
  );
}

export function AuditCopy({ req }: { req: Requisition | null }) {
  if (!req || !req.result) {
    return (
      <p className="p-4 text-[13.5px] leading-6 text-[var(--on-pink-2)]">
        {req?.phase === "error"
          ? `Nothing was filed. ${req.error ?? ""}`
          : "The audit copy records how the answer was made: model tier, grounding check, tokens, cost, trace id and the champion model it read."}
      </p>
    );
  }
  const r = req.result;
  const g = r.grounding ?? {};
  const u = r.usage ?? {};
  const s = stampFor(req);
  const max = Math.max(1, ...r.tool_calls.map((c) => c.latency_ms));

  return (
    <div className="p-4">
      <dl>
        <Row label="Status">
          <span className={s.tone === "errata" ? "text-errata" : undefined}>
            {r.status} ({s.word.toLowerCase()})
          </span>
        </Row>
        <Row label="Model tier">{r.tier}</Row>
        <Row label="Grounding">
          {g.checked != null ? `${((g.score ?? 0) * 100).toFixed(0)}% of ${g.checked} figures traced` : "not run"}
        </Row>
        {g.ungrounded && g.ungrounded.length > 0 && <Row label="Untraced figures">{g.ungrounded.join(", ")}</Row>}
        {r.extra?.revisions != null && r.extra.revisions > 0 && <Row label="Revisions">{r.extra.revisions}</Row>}
        {r.extra?.steps != null && <Row label="Model steps">{r.extra.steps}</Row>}
        <Row label="Tokens in / out">
          {u.input_tokens ?? 0} / {u.output_tokens ?? 0}
        </Row>
        <Row label="Cache read">{u.cache_read_tokens ?? 0} tokens</Row>
        <Row label="Cost">${r.cost_usd.toFixed(4)}</Row>
        <Row label="Latency">{ms(r.latency_ms)}</Row>
        <Row label="Trace id">{r.trace_id ?? "-"}</Row>
        <Row label="Champion run">
          <span title={r.data_version}>{runLabel(r.data_version)}</span>
        </Row>
      </dl>

      {r.tool_calls.length > 0 && (
        <div className="mt-4">
          <h3 className="text-[13px] font-semibold text-type">Tool log</h3>
          <ol className="mt-1">
            {r.tool_calls.map((c, i) => (
              <li key={i} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-pink-2 py-1.5">
                <span className="min-w-0">
                  <span className="block text-[13px] text-type">{toolLabel[c.name] ?? c.name}</span>
                  <span className="num block truncate text-[11.5px] text-[var(--on-pink-2)]">
                    {c.name}({Object.entries(c.input ?? {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <span aria-hidden className="h-[5px] bg-ink" style={{ width: `${Math.max(3, (c.latency_ms / max) * 64)}px` }} />
                  <span className={`num w-16 text-right text-[12px] ${c.is_error ? "text-errata" : "text-ink"}`}>
                    {c.is_error ? "failed" : ms(c.latency_ms)}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
      <p className="mt-4 text-[12px] leading-5 text-[var(--on-pink-2)]">
        Tools are read-only. Purchase orders are proposed and approved only through the decisions ledger.
      </p>
    </div>
  );
}
