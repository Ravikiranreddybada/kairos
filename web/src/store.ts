import { useCallback, useEffect, useReducer, useRef } from "react";
import { streamChat } from "./api";
import type { ChatResult, NodeEvent, Requisition } from "./types";

// The pad lives in this browser only: a convenience, not a record. The real record is the API's memory and audit log.
const KEY = "kairos.pad.v1";

interface Pad {
  sessionId: string;
  nextNo: number;
  items: Requisition[]; // newest first
  openId: string | null; // null = blank form
}

type Action =
  | { type: "open"; id: string | null }
  | { type: "file"; req: Requisition }
  | { type: "node"; id: string; ev: NodeEvent }
  | { type: "done"; id: string; result: ChatResult }
  | { type: "fail"; id: string; error: string }
  | { type: "newPad" };

const newSession = () => `pad-${Math.random().toString(36).slice(2, 10)}`;

function load(): Pad {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const pad = JSON.parse(raw) as Pad;
      // A requisition interrupted by a reload never got its answer.
      pad.items = pad.items.map((r) =>
        r.phase === "routing" ? { ...r, phase: "error", error: "Interrupted before the answer arrived." } : r,
      );
      return pad;
    }
  } catch {
    // storage blocked or corrupt: start a fresh pad
  }
  return { sessionId: newSession(), nextNo: 1, items: [], openId: null };
}

function reduce(pad: Pad, a: Action): Pad {
  const patch = (id: string, f: (r: Requisition) => Requisition) => ({
    ...pad,
    items: pad.items.map((r) => (r.id === id ? f(r) : r)),
  });
  switch (a.type) {
    case "open":
      return { ...pad, openId: a.id };
    case "file":
      return { ...pad, nextNo: pad.nextNo + 1, items: [a.req, ...pad.items], openId: a.req.id };
    case "node":
      return patch(a.id, (r) => ({ ...r, nodes: [...r.nodes, a.ev] }));
    case "done":
      return patch(a.id, (r) => ({ ...r, phase: "done", result: a.result }));
    case "fail":
      return patch(a.id, (r) => ({ ...r, phase: "error", error: a.error }));
    case "newPad":
      return { sessionId: newSession(), nextNo: 1, items: [], openId: null };
  }
}

export function usePad() {
  const [pad, dispatch] = useReducer(reduce, undefined, load);
  const inflight = useRef<AbortController | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(pad));
    } catch {
      // storage full or blocked; the pad still works for this tab
    }
  }, [pad]);

  useEffect(() => () => inflight.current?.abort(), []);

  const submit = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || inflight.current) return;
      const req: Requisition = {
        id: crypto.randomUUID(),
        no: pad.nextNo,
        question: q,
        createdAt: new Date().toISOString(),
        phase: "routing",
        nodes: [],
      };
      dispatch({ type: "file", req });
      const ctrl = new AbortController();
      inflight.current = ctrl;
      try {
        const result = await streamChat(q, pad.sessionId, (ev) => dispatch({ type: "node", id: req.id, ev }), ctrl.signal);
        dispatch({ type: "done", id: req.id, result });
      } catch (e) {
        if ((e as Error).name !== "AbortError") dispatch({ type: "fail", id: req.id, error: (e as Error).message });
      } finally {
        inflight.current = null;
      }
    },
    [pad.nextNo, pad.sessionId],
  );

  const open = useCallback((id: string | null) => dispatch({ type: "open", id }), []);
  const newPad = useCallback(() => {
    inflight.current?.abort();
    dispatch({ type: "newPad" });
  }, []);

  const current = pad.items.find((r) => r.id === pad.openId) ?? null;
  const busy = pad.items.some((r) => r.phase === "routing");
  return { pad, current, busy, submit, open, newPad };
}
