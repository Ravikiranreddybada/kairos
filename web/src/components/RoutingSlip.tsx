import { ms, toolLabel } from "../format";
import type { NodeEvent, Requisition, ToolCall } from "../types";

const LINE: Record<string, string> = {
  guard: "Screened for instruction override",
  route: "Chose the model tier",
  cache: "Checked the answer cache",
  verify: "Checked every figure against tool output",
  finalize: "Attached citations and filed the answer",
};

const NODE_NAME: Record<string, string> = {
  guard: "Guard",
  route: "Route",
  cache: "Cache",
  llm: "Model",
  tools: "Tools",
  verify: "Verify",
  finalize: "File",
};

interface Line {
  key: string;
  node: string;
  text: string;
  calls?: ToolCall[];
}

/** Turn the graph events into slip lines; tool lines pick up their real calls once the result is in. */
function linesOf(nodes: NodeEvent[], calls: ToolCall[] | undefined, cached: boolean): Line[] {
  const queue = [...(calls ?? [])];
  let planned: string[] = [];
  return nodes.map((ev, i) => {
    if (ev.node === "llm") {
      planned = ev.tools ?? [];
      const text = planned.length
        ? `Planned ${planned.length === 1 ? "a tool call" : `${planned.length} tool calls`}`
        : "Wrote the answer from tool results";
      return { key: `${i}`, node: ev.node, text };
    }
    if (ev.node === "tools") {
      const mine = queue.splice(0, planned.length);
      const named = mine.length ? mine : planned.map((name) => ({ name, input: {}, is_error: false, latency_ms: 0 }));
      return { key: `${i}`, node: ev.node, text: "Ran read-only tools", calls: named };
    }
    if (ev.node === "cache" && cached) {
      return { key: `${i}`, node: ev.node, text: "Reused a verified answer for the same question and data" };
    }
    return { key: `${i}`, node: ev.node, text: LINE[ev.node] ?? ev.node };
  });
}

export function RoutingSlip({ req }: { req: Requisition }) {
  const lines = linesOf(req.nodes, req.result?.tool_calls, req.result?.status === "cached");
  const max = Math.max(1, ...(req.result?.tool_calls ?? []).map((c) => c.latency_ms));
  const routing = req.phase === "routing";

  return (
    <div className="border-t border-rule-strong">
      <div className="flex items-baseline justify-between px-4 pt-2 pb-1">
        <span className="caption">Routing slip</span>
        {req.result && <span className="num text-[11.5px] text-type-2">{ms(req.result.latency_ms)} total</span>}
      </div>
      <ol aria-live="polite" className="grid px-4 pb-3">
        {lines.map((l, i) => (
          <li key={l.key} className="lands grid grid-cols-[28px_64px_minmax(0,1fr)] items-baseline gap-x-2 border-b border-rule py-[5px]">
            <span className="num text-[11.5px] text-type-2">{String(i + 1).padStart(2, "0")}</span>
            <span className="text-[13px] font-semibold text-type">{NODE_NAME[l.node] ?? l.node}</span>
            <span className="min-w-0 text-[13px] text-ink">
              {l.text}
              {l.calls && (
                <span className="mt-1 grid gap-1">
                  {l.calls.map((c, j) => (
                    <span key={j} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="num truncate text-[12px]">{c.name}</span>
                        {c.latency_ms > 0 && (
                          <span
                            aria-hidden
                            className="h-[5px] shrink-0 bg-ink"
                            style={{ width: `${Math.max(4, (c.latency_ms / max) * 120)}px` }}
                            title={toolLabel[c.name]}
                          />
                        )}
                      </span>
                      <span className={`num text-[11.5px] ${c.is_error ? "text-errata" : "text-type-2"}`}>
                        {c.is_error ? "failed" : c.latency_ms > 0 ? ms(c.latency_ms) : ""}
                      </span>
                    </span>
                  ))}
                </span>
              )}
            </span>
          </li>
        ))}
        {routing && (
          <li className="grid grid-cols-[28px_64px_minmax(0,1fr)] items-baseline gap-x-2 py-[5px]">
            <span className="num text-[11.5px] text-type-2">{String(lines.length + 1).padStart(2, "0")}</span>
            <span className="pending-mark text-[13px] font-semibold text-type-2">Working</span>
            <span className="text-[13px] text-type-2">Waiting for the next step</span>
          </li>
        )}
      </ol>
    </div>
  );
}
