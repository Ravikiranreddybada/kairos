import { useEffect, useState } from "react";
import { evidenceFor } from "../api";
import { ms, toolLabel } from "../format";
import type { Requisition, ToolCall } from "../types";
import { EvidenceView } from "./evidence/Views";

// Evidence is re-read once per requisition and tool call, then kept for the tab's life.
const cache = new Map<string, Promise<unknown>>();

type State = { kind: "loading" } | { kind: "ok"; data: unknown } | { kind: "error"; message: string } | { kind: "none" };

function useEvidence(key: string, call: ToolCall): { state: State; endpoint?: string } {
  const src = call.is_error ? null : evidenceFor(call);
  const [state, setState] = useState<State>(src ? { kind: "loading" } : { kind: "none" });
  useEffect(() => {
    if (!src) return;
    let live = true;
    let p = cache.get(key);
    if (!p) {
      p = src.load();
      cache.set(key, p);
      p.catch(() => cache.delete(key));
    }
    p.then(
      (data) => live && setState({ kind: "ok", data }),
      (e: Error) => live && setState({ kind: "error", message: e.message }),
    );
    return () => {
      live = false;
    };
    // the key identifies the call; src is derived from it
  }, [key]);
  return { state, endpoint: src?.endpoint };
}

function Inputs({ input }: { input: Record<string, unknown> }) {
  const entries = Object.entries(input ?? {}).filter(([k, v]) => v != null && k !== "query");
  if (!entries.length) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[12px]">
      {entries.map(([k, v]) => (
        <span key={k} className="text-[var(--on-canary-2)]">
          {k.replace(/_/g, " ")} <span className="num text-ink">{String(v)}</span>
        </span>
      ))}
    </div>
  );
}

function EvidenceBlock({ reqId, index, call, citations }: { reqId: string; index: number; call: ToolCall; citations: string[] }) {
  const { state, endpoint } = useEvidence(`${reqId}:${index}`, call);
  return (
    <section className="border-b border-canary-2 px-4 pt-3 pb-4 last:border-b-0" aria-label={toolLabel[call.name] ?? call.name}>
      <header className="flex items-baseline justify-between gap-3">
        <h3 className="text-[14.5px] font-semibold text-type">{toolLabel[call.name] ?? call.name}</h3>
        <span className="num text-[11.5px] text-[var(--on-canary-2)]">{call.is_error ? "failed" : ms(call.latency_ms)}</span>
      </header>
      <Inputs input={call.input} />
      <div className="mt-3">
        {call.is_error ? (
          <p className="text-[13px] text-errata">This tool call failed. The answer did not use it.</p>
        ) : state.kind === "loading" ? (
          <div aria-label="Loading evidence" className="grid gap-2">
            <div className="h-24 bg-canary-2 opacity-60" />
            <div className="h-3 w-2/3 bg-canary-2 opacity-60" />
          </div>
        ) : state.kind === "error" ? (
          <p className="text-[13px] text-errata">Could not reload this evidence. {state.message}</p>
        ) : state.kind === "ok" ? (
          <EvidenceView name={call.name} data={state.data} />
        ) : (
          <EvidenceView name={call.name} data={null} input={call.input} citations={citations} />
        )}
      </div>
      {endpoint && <p className="num mt-3 truncate text-[11px] text-[var(--on-canary-2)]">Re-read from {endpoint}</p>}
    </section>
  );
}

export function EvidenceCopy({ req }: { req: Requisition | null }) {
  if (!req || req.phase === "routing" || !req.result) {
    const text =
      req?.phase === "routing"
        ? "Waiting for the answer. The evidence fills in from the same tools the copilot called."
        : req?.phase === "error"
          ? "No evidence: the requisition was not filed."
          : "Every figure in an answer comes from a read-only tool. This copy shows that tool data, so you can check each number before you act on it.";
    return <p className="p-4 text-[13.5px] leading-6 text-[var(--on-canary-2)]">{text}</p>;
  }
  const calls = req.result.tool_calls;
  if (!calls.length) {
    return (
      <p className="p-4 text-[13.5px] leading-6 text-[var(--on-canary-2)]">
        {req.result.status === "blocked"
          ? "The guard refused this request before any tool ran."
          : "This answer called no tools, so there is no evidence to show."}
      </p>
    );
  }
  return (
    <div>
      {calls.map((c, i) => (
        <EvidenceBlock key={`${req.id}:${i}`} reqId={req.id} index={i} call={c} citations={req.result!.citations} />
      ))}
    </div>
  );
}
