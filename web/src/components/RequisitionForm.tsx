import { ArrowElbowDownLeft, ArrowRight, Plus } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { reqNo, stampDate, subjectOf } from "../format";
import type { Requisition } from "../types";
import { AnswerBody } from "./AnswerBody";
import { RoutingSlip } from "./RoutingSlip";
import { Stamp } from "./Stamp";

const EXAMPLES = [
  "What should I reorder at S01 this week?",
  "What if the supplier is 5 days late for SKU002 at S01?",
  "What does the inventory policy say about service levels?",
];

interface Props {
  req: Requisition | null;
  sessionId: string;
  nextNo: number;
  busy: boolean;
  onSubmit: (q: string) => void;
  onNew: () => void;
}

function Cell({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`cell ${className}`}>
      <div className="caption">{label}</div>
      <div className="num mt-0.5 truncate text-[13.5px] text-ink">{children}</div>
    </div>
  );
}

function Header({ no, date, sessionId, tier, subject }: { no: number; date: string; sessionId: string; tier?: string; subject?: string | null }) {
  return (
    <div className="grid grid-cols-2 border-b border-rule-strong sm:grid-cols-[minmax(0,1.4fr)_repeat(4,minmax(0,1fr))]">
      <div className="cell col-span-2 flex items-end border-b border-rule sm:col-span-1 sm:border-b-0">
        <h1 className="wordmark text-[22px] leading-7 text-type">Requisition</h1>
      </div>
      <Cell label="No.">{reqNo(no)}</Cell>
      <Cell label="Date" className="sm:border-r">{stampDate(date)}</Cell>
      <Cell label="Subject" className="border-t border-rule sm:border-t-0">{subject ?? "-"}</Cell>
      <Cell label="Model tier" className="border-t border-rule sm:border-t-0">
        {tier ? (tier === "strong" ? "Strong" : tier === "fast" ? "Fast" : tier) : "-"}
      </Cell>
      <span className="sr-only">Session {sessionId}</span>
    </div>
  );
}

function Composer({ busy, onSubmit }: { busy: boolean; onSubmit: (q: string) => void }) {
  const [q, setQ] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const send = () => {
    if (q.trim() && !busy) onSubmit(q);
  };
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
    >
      <div className="px-4 pt-3">
        <label htmlFor="question" className="caption">
          Question
        </label>
        <textarea
          id="question"
          ref={ref}
          rows={3}
          maxLength={2000}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Ask about a store, a SKU, a forecast or a policy"
          className="ruled filled mt-1 block w-full resize-y bg-transparent text-[16px] outline-none placeholder:text-type-2"
        />
      </div>

      <fieldset className="mt-3 border-t border-rule-strong px-4 pt-2 pb-3">
        <legend className="sr-only">Common requisitions</legend>
        <div className="caption pb-1">Common requisitions</div>
        <div className="grid max-w-[60ch]">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => {
                setQ(ex);
                ref.current?.focus();
              }}
              className="flex cursor-pointer items-baseline gap-2 border-b border-rule py-1.5 text-left text-[13.5px] text-type
                transition-colors duration-150 hover:text-ink"
            >
              <ArrowRight aria-hidden size={13} className="shrink-0 translate-y-[2px] text-rule-ink" />
              {ex}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule-strong px-4 py-3">
        <span className="text-[12.5px] text-type-2">
          <span className="kbd">Enter</span> submits, <span className="kbd">Shift</span>+<span className="kbd">Enter</span> adds a line
        </span>
        <button type="submit" className="btn" disabled={busy || !q.trim()}>
          Submit
          <ArrowElbowDownLeft size={16} />
        </button>
      </div>
      {busy && <p className="px-4 pb-3 text-[12.5px] text-type-2">Another requisition is still routing. Submit when it is filed.</p>}
    </form>
  );
}

export function RequisitionForm({ req, sessionId, nextNo, busy, onSubmit, onNew }: Props) {
  if (!req) {
    return (
      <article className="stack mb-4">
        <div className="sheet">
          <Header no={nextNo} date={new Date().toISOString()} sessionId={sessionId} />
          <Composer busy={busy} onSubmit={onSubmit} />
        </div>
      </article>
    );
  }

  const res = req.result;
  return (
    <article className="stack mb-4" aria-busy={req.phase === "routing"}>
      <div className="sheet">
        <Header no={req.no} date={req.createdAt} sessionId={sessionId} tier={res?.tier} subject={subjectOf(res?.tool_calls)} />

        <div className="px-4 pt-3 pb-3">
          <div className="caption">Question</div>
          <p className="ruled filled mt-1 text-[16px]">{req.question}</p>
        </div>

        <RoutingSlip req={req} />

        <div className="border-t border-rule-strong px-4 pt-2 pb-4">
          <div className="caption pb-1">Answer</div>
          {res ? (
            <AnswerBody result={res} />
          ) : req.phase === "error" ? (
            <p className="ruled text-[15px] text-errata">{req.error}</p>
          ) : (
            <p className="ruled pending-mark text-[15px] text-type-2">Being typed</p>
          )}

          {res && res.citations.length > 0 && (
            <div className="mt-3">
              <div className="caption">Cited</div>
              <ul className="mt-1 flex flex-wrap gap-2">
                {res.citations.map((c) => (
                  <li key={c} className="num border border-rule-strong px-2 py-0.5 text-[12px] text-ink">
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(res || req.phase === "error") && (
            <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
              <button type="button" className="btn btn-quiet" onClick={onNew} disabled={busy}>
                <Plus size={15} />
                Follow-up requisition
              </button>
              <div className="pr-2 pb-1">
                <Stamp req={req} />
              </div>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
