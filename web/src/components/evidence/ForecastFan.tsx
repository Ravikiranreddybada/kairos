import { useState } from "react";
import { units } from "../../format";
import type { Forecast } from "../../types";

const W = 400;
const H = 160;
const PAD = { l: 34, r: 8, t: 8, b: 22 };

const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

/** Daily forecast with its 80% interval as a band. Drawn from the API data, nothing else. */
export function ForecastFan({ f }: { f: Forecast }) {
  const [hover, setHover] = useState<number | null>(null);
  const d = f.daily;
  if (!d.length) return <p className="text-[13px]">No forecast rows for this series.</p>;

  const top = Math.max(...d.map((p) => p.hi)) * 1.08 || 1;
  const x = (i: number) => PAD.l + (i / Math.max(1, d.length - 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - v / top) * (H - PAD.t - PAD.b);
  const band =
    d.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.hi).toFixed(1)}`).join("") +
    d.map((_, i) => `L${x(d.length - 1 - i).toFixed(1)},${y(d[d.length - 1 - i].lo).toFixed(1)}`).join("") +
    "Z";
  const line = d.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.yhat).toFixed(1)}`).join("");
  const ticks = [0, top / 2, top].map((v) => Math.round(v));
  const weeks = d.map((_, i) => i).filter((i) => i % 7 === 0);
  const h = hover != null ? d[hover] : null;

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    const i = Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (d.length - 1));
    setHover(Math.min(d.length - 1, Math.max(0, i)));
  };

  return (
    <figure>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 text-[13px]">
        <span>
          <span className="num text-[20px] text-ink">{units(f.total_units)}</span>{" "}
          <span className="text-[var(--on-canary-2)]">units over {f.horizon_days} days</span>
        </span>
        <span className="num text-[12px] text-ink" aria-live="polite">
          {h ? `${day(h.date)}: ${units(h.yhat)} (${units(h.lo)} to ${units(h.hi)})` : `${f.interval} interval ${units(f.total_lo)} to ${units(f.total_hi)}`}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="mt-2 block w-full touch-none"
        role="img"
        aria-label={`Daily demand forecast for ${f.store_id} ${f.sku_id}, ${f.horizon_days} days, with ${f.interval} interval.`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} stroke="var(--canary-2)" strokeWidth={1} />
            <text x={PAD.l - 6} y={y(t) + 3.5} textAnchor="end" className="num" fontSize={9.5} fill="var(--on-canary-2)">
              {t}
            </text>
          </g>
        ))}
        <path d={band} fill="var(--ink-band)" />
        <path d={line} fill="none" stroke="var(--ink)" strokeWidth={1.6} strokeLinejoin="round" />
        {weeks.map((i) => (
          <text key={i} x={x(i)} y={H - 6} textAnchor={i === 0 ? "start" : "middle"} className="num" fontSize={9.5} fill="var(--on-canary-2)">
            {day(d[i].date)}
          </text>
        ))}
        {h && hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b} stroke="var(--ink)" strokeWidth={1} />
            <rect x={x(hover) - 3} y={y(h.yhat) - 3} width={6} height={6} fill="var(--ink)" />
          </g>
        )}
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-x-4 text-[12px] text-[var(--on-canary-2)]">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-[2px] w-4 bg-ink" /> point forecast
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-2.5 w-4 bg-[var(--ink-band)]" /> {f.interval} interval
        </span>
        <span>
          model <span className="num text-ink">{f.model}</span>
        </span>
      </figcaption>
      <table className="sr-only-table">
        <caption>Daily forecast</caption>
        <thead>
          <tr>
            <th>Date</th>
            <th>Forecast</th>
            <th>Low</th>
            <th>High</th>
          </tr>
        </thead>
        <tbody>
          {d.map((p) => (
            <tr key={p.date}>
              <td>{p.date}</td>
              <td>{p.yhat}</td>
              <td>{p.lo}</td>
              <td>{p.hi}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
