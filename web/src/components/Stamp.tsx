import { stampDate } from "../format";
import type { Requisition } from "../types";

export type Tone = "ink" | "errata" | "quiet";

export function stampFor(r: Requisition): { word: string; note: string; tone: Tone } {
  if (r.phase === "error") return { word: "NOT FILED", note: "No answer came back", tone: "errata" };
  const res = r.result;
  if (!res) return { word: "ROUTING", note: "", tone: "quiet" };
  const g = res.grounding ?? {};
  const checked = g.checked ?? 0;
  const bad = g.ungrounded?.length ?? 0;
  switch (res.status) {
    case "blocked":
      return { word: "REFUSED", note: "Instruction override blocked", tone: "errata" };
    case "degraded":
      return { word: "DEGRADED", note: "Model offline, tool results only", tone: "quiet" };
    case "budget_exhausted":
      return { word: "PARTIAL", note: "Step budget reached", tone: "quiet" };
  }
  if (g.passed === false) return { word: "UNVERIFIED", note: `${bad} of ${checked} figures untraced`, tone: "errata" };
  if (checked === 0) return { word: "VERIFIED", note: "No figures to trace", tone: "ink" };
  if (res.status === "cached") return { word: "VERIFIED", note: `From cache, ${checked - bad} of ${checked} figures traced`, tone: "ink" };
  return { word: "VERIFIED", note: `${checked - bad} of ${checked} figures traced to tools`, tone: "ink" };
}

export function Stamp({ req }: { req: Requisition }) {
  const s = stampFor(req);
  return (
    <div className="stamp lands" data-tone={s.tone} role="img" aria-label={`${s.word}. ${s.note}`}>
      <span className="stamp-word">{s.word}</span>
      <span className="text-[11px] font-semibold leading-4" style={{ fontStretch: "85%" }}>
        {s.note}
      </span>
      <span className="num text-[10.5px] leading-4">{stampDate(req.createdAt)}</span>
    </div>
  );
}
