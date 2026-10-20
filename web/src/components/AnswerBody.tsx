import type { ReactNode } from "react";
import type { ChatResult } from "../types";

const DEGRADED_PREFIX = /^\(AI summary unavailable.*?\)\n?/;
const UNVERIFIED_SUFFIX = /\n*\W*Some figures above could not be verified against tool outputs\.?\s*$/u;
// Inline source refs, then identifiers (stores, SKUs, run ids), then free-standing figures.
const TOKEN =
  /(\[source:\s*[^\]]+\])|((?:SKU\d{3}|S\d{2}|\d{8}T\d+Z)(?![A-Za-z\d]))|((?<![A-Za-z_\d.])-?\d[\d,]*(?:\.\d+)?%?(?![A-Za-z_\d]))/g;

export function cleanAnswer(answer: string): string {
  return answer.replace(DEGRADED_PREFIX, "").replace(UNVERIFIED_SUFFIX, "").trim();
}

const norm = (s: string) => s.replace(/[,%]/g, "").replace(/\.0+$/, "");

function inline(text: string, ungrounded: Set<string>): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    if (m[1]) {
      const ref = m[1].replace(/^\[source:\s*/, "").replace(/\]$/, "");
      out.push(
        <cite key={at} className="num mx-0.5 border-b border-ink px-0.5 text-[12px] not-italic text-ink-2">
          {ref}
        </cite>,
      );
    } else if (m[2]) {
      out.push(
        <span key={at} className="num text-[0.92em]">
          {m[2]}
        </span>,
      );
    } else {
      // Figures stay in the sans at tabular width: mono figures inside prose read as spaced-out digits.
      const bad = ungrounded.has(norm(m[3]));
      out.push(
        <span
          key={at}
          className={`font-semibold tabular-nums ${bad ? "bg-[var(--errata-wash)] text-errata underline decoration-wavy underline-offset-4" : ""}`}
          title={bad ? "Not found in any tool result" : undefined}
        >
          {m[3]}
        </span>,
      );
    }
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** The typed-in answer: carbon ink on ruled lines, figures in tabular weight, identifiers in the data face. */
export function AnswerBody({ result }: { result: ChatResult }) {
  const ungrounded = new Set((result.grounding?.ungrounded ?? []).map(norm));
  const lines = cleanAnswer(result.answer).split("\n");
  const blocks: ReactNode[] = [];
  let list: ReactNode[] = [];
  const flush = () => {
    if (list.length) blocks.push(<ul key={`l${blocks.length}`} className="list-none">{list}</ul>);
    list = [];
  };
  lines.forEach((line, i) => {
    const item = /^\s*[-*]\s+(.*)$/.exec(line);
    if (item) {
      list.push(
        <li key={i} className="grid grid-cols-[18px_minmax(0,1fr)]">
          <span aria-hidden>-</span>
          <span>{inline(item[1], ungrounded)}</span>
        </li>,
      );
      return;
    }
    flush();
    if (line.trim()) blocks.push(<p key={i}>{inline(line, ungrounded)}</p>);
  });
  flush();

  return <div className="ruled filled max-w-[72ch] text-[15.5px]">{blocks}</div>;
}
