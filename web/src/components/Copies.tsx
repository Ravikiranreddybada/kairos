import { useId, useState } from "react";
import type { Requisition } from "../types";
import { AuditCopy } from "./AuditCopy";
import { EvidenceCopy } from "./EvidenceCopy";

type Copy = "evidence" | "audit";

const COPIES: { id: Copy; label: string; sheet: string; edge: string }[] = [
  { id: "evidence", label: "Evidence copy", sheet: "bg-canary", edge: "bg-canary-2" },
  { id: "audit", label: "Audit copy", sheet: "bg-pink", edge: "bg-pink-2" },
];

export function Copies({ req }: { req: Requisition | null }) {
  const [copy, setCopy] = useState<Copy>("evidence");
  const base = useId();
  const active = COPIES.find((c) => c.id === copy)!;

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const next = copy === "evidence" ? "audit" : "evidence";
    setCopy(next);
    document.getElementById(`${base}-${next}-tab`)?.focus();
  };

  return (
    <div>
      <div role="tablist" aria-label="Copies of this requisition" className="flex gap-1" onKeyDown={onKey}>
        {COPIES.map((c) => {
          const on = c.id === copy;
          return (
            <button
              key={c.id}
              id={`${base}-${c.id}-tab`}
              role="tab"
              type="button"
              aria-selected={on}
              aria-controls={`${base}-${c.id}-panel`}
              tabIndex={on ? 0 : -1}
              onClick={() => setCopy(c.id)}
              className={`h-9 cursor-pointer border border-b-0 border-rule-strong px-4 text-[13.5px] font-semibold transition-[height,color]
                duration-150 ${on ? `${c.sheet} self-end text-type` : `${c.edge} mt-1.5 h-[30px] self-end text-type-2 hover:text-type`}`}
            >
              {c.label}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={`${base}-${copy}-panel`}
        aria-labelledby={`${base}-${copy}-tab`}
        className={`${active.sheet} border border-rule-strong`}
      >
        {copy === "evidence" ? <EvidenceCopy req={req} /> : <AuditCopy req={req} />}
      </div>
    </div>
  );
}
