import type { ChatResult, ModelCard, NodeEvent, ToolCall } from "./types";

// The Vite proxy adds X-API-Key; the browser only ever talks to /v1 on its own origin.

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function readError(res: Response): Promise<ApiError> {
  let detail = res.statusText || "request failed";
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    // body was not JSON; keep the status text
  }
  if (res.status === 429) {
    const retry = res.headers.get("Retry-After");
    detail = `Rate limit reached. Try again in ${retry ?? "a few"} seconds.`;
  }
  if (res.status === 401) detail = "The API rejected the key. Check KAIROS_WEB_API_KEY for the dev proxy.";
  return new ApiError(detail, res.status);
}

async function getJson<T>(path: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { ...init, signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("The Kairos API is not reachable. Start it with `kairos serve`.", 0);
  }
  if (!res.ok) throw await readError(res);
  return (await res.json()) as T;
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export const fetchModel = (signal?: AbortSignal) => getJson<ModelCard>("/v1/model", undefined, signal);

/** Stream one copilot turn. Calls onNode for each graph step, resolves with the final result. */
export async function streamChat(
  message: string,
  sessionId: string,
  onNode: (ev: NodeEvent) => void,
  signal?: AbortSignal,
): Promise<ChatResult> {
  let res: Response;
  try {
    res = await fetch("/v1/agent/chat/stream", { ...post({ message, session_id: sessionId }), signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("The Kairos API is not reachable. Start it with `kairos serve`.", 0);
  }
  if (!res.ok || !res.body) throw await readError(res);

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let result: ChatResult | undefined;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const data = frame
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trimStart())
        .join("\n");
      if (!data) continue;
      const ev = JSON.parse(data);
      if (ev.event === "node") onNode(ev as NodeEvent);
      else if (ev.event === "result") {
        const { event: _event, ...rest } = ev;
        result = rest as ChatResult;
      }
    }
  }
  if (!result) throw new ApiError("The stream ended before the answer arrived.", 0);
  return result;
}

// ------------------------------------------------------------ evidence
// Each read-only tool has a REST twin. The evidence copy re-reads it with the same inputs.

type In = Record<string, unknown>;
const str = (v: unknown) => (v == null ? undefined : String(v));
function qs(params: Record<string, unknown>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export interface EvidenceSource {
  endpoint: string;
  load: (signal?: AbortSignal) => Promise<unknown>;
}

export function evidenceFor(call: ToolCall): EvidenceSource | null {
  const a: In = call.input ?? {};
  const store = str(a.store_id);
  const sku = str(a.sku_id);
  switch (call.name) {
    case "get_forecast": {
      const path = `/v1/forecast/${store}/${sku}${qs({ horizon_days: a.horizon_days })}`;
      return { endpoint: `GET ${path}`, load: (s) => getJson(path, undefined, s) };
    }
    case "explain_forecast": {
      const path = `/v1/forecast/${store}/${sku}/explain${qs({ horizon_days: a.horizon_days })}`;
      return { endpoint: `GET ${path}`, load: (s) => getJson(path, undefined, s) };
    }
    case "inventory_policy": {
      const body = { store_id: store, sku_id: sku, service_level: a.service_level ?? undefined,
        lead_time_override_days: a.lead_time_override_days ?? undefined };
      return { endpoint: "POST /v1/inventory/policy", load: (s) => getJson("/v1/inventory/policy", post(body), s) };
    }
    case "reorder_worklist": {
      const path = `/v1/inventory/worklist/${store}${qs({ service_level: a.service_level, top_k: a.top_k })}`;
      return { endpoint: `GET ${path}`, load: (s) => getJson(path, undefined, s) };
    }
    case "simulate_supply_risk": {
      const body = { store_id: store, sku_id: sku, service_level: a.service_level ?? undefined,
        lead_time_delay_days: a.lead_time_delay_days ?? 0, demand_shock_pct: a.demand_shock_pct ?? 0 };
      return { endpoint: "POST /v1/inventory/stress-test",
        load: (s) => getJson("/v1/inventory/stress-test", post(body), s) };
    }
    case "network_pooling": {
      const path = `/v1/inventory/network/${sku}${qs({ service_level: a.service_level, dc_to_store_days: a.dc_to_store_days })}`;
      return { endpoint: `GET ${path}`, load: (s) => getJson(path, undefined, s) };
    }
    case "what_if_promo": {
      const body = { store_id: store, sku_id: sku, start_date: a.start_date ?? undefined, days: a.days ?? 7 };
      return { endpoint: "POST /v1/whatif/promo", load: (s) => getJson("/v1/whatif/promo", post(body), s) };
    }
    case "model_health": {
      const path = `/v1/model/health${qs({ top_k: a.top_k })}`;
      return { endpoint: `GET ${path}`, load: (s) => getJson(path, undefined, s) };
    }
    case "detect_anomalies": {
      const path = `/v1/anomalies${qs({ store_id: store, sku_id: sku, limit: a.top_k ?? 5 })}`;
      return { endpoint: `GET ${path}`, load: (s) => getJson(path, undefined, s) };
    }
    case "decision_history": {
      const path = `/v1/decisions/proposals${qs({ store_id: store, sku_id: sku, status: a.status, limit: a.limit })}`;
      return { endpoint: `GET ${path}`, load: (s) => getJson(path, undefined, s) };
    }
    default:
      return null; // run_sql, search_docs, browse_docs: shown from their inputs and the answer's citations
  }
}
