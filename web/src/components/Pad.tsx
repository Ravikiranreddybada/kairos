import { ArrowCounterClockwise, CaretDown, Plus } from "@phosphor-icons/react";
import { clock, reqNo, subjectOf } from "../format";
import type { Requisition } from "../types";
import { stampFor } from "./Stamp";

interface PadProps {
  items: Requisition[];
  openId: string | null;
  sessionId: string;
  busy: boolean;
  onOpen: (id: string | null) => void;
  onNewPad: () => void;
}

function statusWord(r: Requisition): { word: string; tone: "ink" | "errata" | "quiet" } {
  if (r.phase === "routing") return { word: "Routing", tone: "quiet" };
  const s = stampFor(r);
  return { word: s.word.toLowerCase().replace(/^\w/, (c) => c.toUpperCase()), tone: s.tone };
}

function PadList({ items, openId, onOpen }: Pick<PadProps, "items" | "openId" | "onOpen">) {
  if (!items.length) {
    return (
      <p className="px-4 py-3 text-[13px] leading-5 text-type-2">
        Filed requisitions stack here. Each one keeps its answer, evidence and audit copy.
      </p>
    );
  }
  return (
    <ol className="grid">
      {items.map((r) => {
        const open = r.id === openId;
        const status = statusWord(r);
        const subject = subjectOf(r.result?.tool_calls);
        return (
          <li key={r.id}>
            <button
              type="button"
              onClick={() => onOpen(r.id)}
              aria-current={open ? "true" : undefined}
              className={`grid w-full cursor-pointer gap-1 border-b border-rule px-4 py-3 text-left transition-colors duration-150
                ${open ? "bg-sheet" : "hover:bg-[var(--ink-wash)]"}`}
            >
              <span className="flex items-baseline justify-between gap-2 text-[12px]">
                <span className="num text-ink">No. {reqNo(r.no)}</span>
                <span className="num text-type-2">{clock(r.createdAt)}</span>
              </span>
              <span className="line-clamp-2 text-[13.5px] leading-[19px] text-type">{r.question}</span>
              <span className="flex items-baseline justify-between gap-2 text-[12px]">
                <span className="num truncate text-type-2">{subject ?? ""}</span>
                <span
                  className={`font-semibold ${
                    status.tone === "errata" ? "text-errata" : status.tone === "quiet" ? "text-type-2" : "text-ink"
                  } ${r.phase === "routing" ? "pending-mark" : ""}`}
                >
                  {status.word}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function PadFoot({ sessionId, onNewPad, busy }: Pick<PadProps, "sessionId" | "onNewPad" | "busy">) {
  return (
    <div className="grid gap-2 border-t border-rule-strong px-4 py-3 text-[12px] text-type-2">
      <span>
        Session <span className="num text-ink">{sessionId}</span>
      </span>
      <span className="leading-4">The copilot remembers preferences, like a target service level, within one pad.</span>
      <button type="button" onClick={onNewPad} disabled={busy} className="btn btn-quiet h-8 justify-self-start px-3 text-[13px]">
        <ArrowCounterClockwise size={15} />
        Start a new pad
      </button>
    </div>
  );
}

export function Pad({ items, openId, sessionId, busy, onOpen, onNewPad }: PadProps) {
  return (
    <div className="flex min-h-full flex-col">
      <div className="border-b border-rule-strong p-4">
        <button type="button" onClick={() => onOpen(null)} className="btn w-full justify-center" disabled={openId === null}>
          <Plus size={16} weight="bold" />
          New requisition
        </button>
      </div>
      <div className="flex-1">
        <PadList items={items} openId={openId} onOpen={onOpen} />
      </div>
      <PadFoot sessionId={sessionId} onNewPad={onNewPad} busy={busy} />
    </div>
  );
}

/** Below the lg breakpoint the pad folds into a disclosure above the form. */
export function MobilePad({ items, openId, sessionId, busy, onOpen, onNewPad }: PadProps) {
  return (
    <div className="mb-4 flex gap-2 lg:hidden">
      <details className="group sheet min-w-0 flex-1">
        <summary className="flex h-10 cursor-pointer list-none items-center justify-between gap-2 px-3 text-[14px] font-semibold text-ink">
          Pad
          <span className="flex items-center gap-2 text-type-2">
            <span className="num text-[12px]">{items.length} filed</span>
            <CaretDown size={14} className="transition-transform duration-150 group-open:rotate-180" />
          </span>
        </summary>
        <div className="max-h-[50dvh] overflow-y-auto border-t border-rule-strong bg-ground-2">
          <PadList items={items} openId={openId} onOpen={onOpen} />
          <PadFoot sessionId={sessionId} onNewPad={onNewPad} busy={busy} />
        </div>
      </details>
      <button type="button" onClick={() => onOpen(null)} className="btn" disabled={openId === null} aria-label="New requisition">
        <Plus size={16} weight="bold" />
        <span className="hidden sm:inline">New</span>
      </button>
    </div>
  );
}
