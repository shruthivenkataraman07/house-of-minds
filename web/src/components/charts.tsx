"use client";
/**
 * Small, precise SVG charts (no extra dependency). Every mark is a real data value from the API,
 * is keyboard-focusable, carries a text label (not color alone) and calls back on click.
 */
import { type KeyboardEvent, useMemo } from "react";

export type ChartTone = "pos" | "neg" | "warn" | "accent" | "muted";
const FILL: Record<ChartTone, string> = { pos: "var(--pos)", neg: "var(--neg)", warn: "var(--warn)", accent: "var(--accent)", muted: "var(--chart-2)" };
const act = (fn?: () => void) => ({
  role: fn ? "button" : undefined, tabIndex: fn ? 0 : undefined, onClick: fn,
  onKeyDown: fn ? (e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(); } } : undefined,
  style: fn ? { cursor: "pointer" } : undefined,
});

/** Aligned horizontal bars around zero, with optional tested-range whisker (low..high). */
export function ValueBars({ rows, format, label, selected }: {
  rows: { key: string; label: string; value: number | null; low?: number | null; high?: number | null; tone: ChartTone; note?: string; onClick?: () => void }[];
  format: (v: number) => string; label: string; selected?: string | null;
}) {
  const vals = rows.flatMap((r) => [r.value ?? 0, r.low ?? r.value ?? 0, r.high ?? r.value ?? 0, 0]);
  const min = Math.min(...vals), max = Math.max(...vals);
  const W = 640, L = 170, R = 96, rowH = 34;
  const x = (v: number) => L + ((v - min) / (max - min || 1)) * (W - L - R);
  const H = rows.length * rowH + 22;
  return (
    <div className="overflow-x-auto"><svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[520px]" role="group" aria-label={label}>
      <line x1={x(0)} x2={x(0)} y1={4} y2={H - 18} stroke="var(--line-strong)" />
      <text x={x(0)} y={H - 4} textAnchor="middle" fontSize="11" fill="var(--muted)">$0</text>
      {rows.map((r, i) => {
        const y = i * rowH + 8;
        const v = r.value;
        const sel = selected === r.key;
        return (
          <g key={r.key} {...act(r.onClick)} aria-label={`${r.label}: ${v === null ? "not available" : format(v)}${r.low != null && r.high != null ? `, tested range ${format(r.low)} to ${format(r.high)}` : ""}`}>
            <rect x={0} y={y - 4} width={W} height={rowH - 2} fill={sel ? "var(--accent-soft)" : "transparent"} />
            <text x={8} y={y + 15} fontSize="12.5" fill="var(--text)" fontWeight={sel ? 600 : 400}>{r.label}</text>
            {r.note && <text x={8} y={y + 27} fontSize="10.5" fill="var(--muted)">{r.note}</text>}
            {v !== null && <rect x={Math.min(x(0), x(v))} y={y + 5} width={Math.max(1.5, Math.abs(x(v) - x(0)))} height={14} rx={2} fill={FILL[r.tone]} opacity={0.85} />}
            {r.low != null && r.high != null && r.low !== r.high && (
              <g stroke="var(--text)" strokeWidth={1.2}>
                <line x1={x(r.low)} x2={x(r.high)} y1={y + 12} y2={y + 12} />
                <line x1={x(r.low)} x2={x(r.low)} y1={y + 7} y2={y + 17} /><line x1={x(r.high)} x2={x(r.high)} y1={y + 7} y2={y + 17} />
              </g>)}
            <text x={W - 4} y={y + 16} fontSize="12.5" textAnchor="end" fill={v === null ? "var(--muted)" : v < 0 ? "var(--neg)" : "var(--text)"} style={{ fontVariantNumeric: "tabular-nums" }}>{v === null ? "n/a" : format(v)}</text>
          </g>);
      })}
    </svg></div>
  );
}

/** Part-to-whole bar with labelled, clickable segments. */
export function CompositionBar({ segments, label, selected }: {
  segments: { key: string; label: string; value: number; display?: string; tone: ChartTone; onClick?: () => void }[]; label: string; selected?: string | null;
}) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  const starts = segments.map((_, i) => segments.slice(0, i).reduce((a, x) => a + (x.value / total) * 600, 0));
  return (
    <div>
      <svg viewBox="0 0 600 28" className="w-full" role="group" aria-label={label} preserveAspectRatio="none">
        {segments.map((s, i) => {
          const w = (s.value / total) * 600; const x0 = starts[i];
          return <rect key={s.key} x={x0} y={0} width={Math.max(0, w - 2)} height={28} rx={2} fill={FILL[s.tone]} opacity={selected && selected !== s.key ? 0.35 : 0.9}
            {...act(s.onClick)} aria-label={`${s.label}: ${s.display ?? s.value}`}><title>{`${s.label}: ${s.display ?? s.value}`}</title></rect>;
        })}
      </svg>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {segments.map((s) => (
          <li key={s.key}><button type="button" onClick={s.onClick} className={`flex items-center gap-1.5 text-[12.5px] ${selected === s.key ? "font-semibold" : ""}`}>
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: FILL[s.tone] }} />{s.label} <span className="num text-muted">{s.display ?? s.value}</span></button></li>))}
      </ul>
    </div>
  );
}

/** Two positions per row on one shared rank scale (1 = weakest). */
export function RankDumbbell({ rows, max, aLabel, bLabel, label, selected }: {
  rows: { key: string; label: string; a: number; b: number; onClick?: () => void }[]; max: number; aLabel: string; bLabel: string; label: string; selected?: string | null;
}) {
  const W = 640, L = 70, R = 16, rowH = 24, H = rows.length * rowH + 40;
  const x = (v: number) => L + ((v - 1) / (max - 1)) * (W - L - R);
  const ticks = [1, Math.round(max / 4), Math.round(max / 2), Math.round((3 * max) / 4), max];
  return (
    <div className="overflow-x-auto"><svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[520px]" role="group" aria-label={label}>
      {ticks.map((t) => <g key={t}><line x1={x(t)} x2={x(t)} y1={6} y2={H - 26} stroke="var(--line)" /><text x={x(t)} y={H - 12} fontSize="10.5" textAnchor="middle" fill="var(--muted)">{t}</text></g>)}
      <text x={W - R} y={H - 1} fontSize="10.5" textAnchor="end" fill="var(--muted)">← weaker · position among {max} machines · stronger →</text>
      {rows.map((r, i) => {
        const y = i * rowH + 16; const sel = selected === r.key;
        return (
          <g key={r.key} {...act(r.onClick)} aria-label={`${r.label}: ${aLabel} ${r.a}, ${bLabel} ${r.b}`}>
            <rect x={0} y={y - 11} width={W} height={rowH - 2} fill={sel ? "var(--accent-soft)" : "transparent"} />
            <text x={6} y={y + 4} fontSize="12" fill="var(--text)" fontWeight={sel ? 600 : 400}>{r.label}</text>
            <line x1={x(r.a)} x2={x(r.b)} y1={y} y2={y} stroke="var(--line-strong)" strokeWidth={2} />
            <circle cx={x(r.a)} cy={y} r={5} fill="var(--neg)"><title>{`${aLabel}: ${r.a}`}</title></circle>
            <circle cx={x(r.b)} cy={y} r={5} fill="var(--accent)"><title>{`${bLabel}: ${r.b}`}</title></circle>
          </g>);
      })}
    </svg></div>
  );
}

/** Rows x columns intensity grid with value labels. */
export function MatrixHeat({ rows, cols, value, format, label, onCell, selectedRow }: {
  rows: { key: string; label: string }[]; cols: { key: string; label: string }[];
  value: (r: string, c: string) => number | null; format: (v: number) => string; label: string;
  onCell?: (r: string, c: string) => void; selectedRow?: string | null;
}) {
  const vals = rows.flatMap((r) => cols.map((c) => value(r.key, c.key))).filter((v): v is number => v !== null);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-[3px] text-[12px]" aria-label={label}>
        <thead><tr><th /> {cols.map((c) => <th key={c.key} className="label px-1 text-center font-normal">{c.label}</th>)}</tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.key}>
            <th scope="row" className={`whitespace-nowrap pr-2 text-left font-normal ${selectedRow === r.key ? "font-semibold" : ""}`}>{r.label}</th>
            {cols.map((c) => {
              const v = value(r.key, c.key);
              const t = v === null ? 0 : (v - lo) / (hi - lo || 1);
              return (
                <td key={c.key} className={`num h-8 min-w-[54px] rounded text-center ${onCell && v !== null ? "cursor-pointer" : ""}`} title={v === null ? "no data" : `${r.label} · ${c.label}: ${format(v)}`}
                  {...act(onCell && v !== null ? () => onCell(r.key, c.key) : undefined)}
                  style={{ background: v === null ? "var(--surface-2)" : `color-mix(in srgb, var(--accent) ${Math.round(8 + t * 72)}%, var(--surface))`, color: t > 0.55 ? "white" : "var(--text)" }}>
                  {v === null ? "—" : format(v)}
                </td>);
            })}
          </tr>))}</tbody>
      </table>
    </div>
  );
}

/** GitHub-style calendar: weeks as columns, weekdays as rows. */
export function CalendarHeat({ days, label, format, onDay, selected }: {
  days: { date: string; value: number; flag?: boolean }[]; label: string; format: (v: number) => string;
  onDay?: (date: string) => void; selected?: string | null;
}) {
  const cells = useMemo(() => {
    if (!days.length) return [];
    const first = new Date(`${days[0].date}T00:00:00Z`);
    const offset = (first.getUTCDay() + 6) % 7;
    return days.map((d, i) => ({ ...d, col: Math.floor((i + offset) / 7), row: (i + offset) % 7 }));
  }, [days]);
  if (!cells.length) return <p className="label">No days in the selected period.</p>;
  const lo = Math.min(...days.map((d) => d.value)), hi = Math.max(...days.map((d) => d.value));
  const cols = cells[cells.length - 1].col + 1, S = 14, G = 3, L = 26;
  const W = L + cols * (S + G), H = 7 * (S + G) + 18;
  const months = cells.filter((c) => c.date.endsWith("-01") || c === cells[0]);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[680px]" role="group" aria-label={label}>
      {["Mon", "", "Wed", "", "Fri", "", "Sun"].map((d, i) => <text key={i} x={0} y={18 + i * (S + G) + 10} fontSize="9.5" fill="var(--muted)">{d}</text>)}
      {months.map((m) => <text key={m.date} x={L + m.col * (S + G)} y={10} fontSize="9.5" fill="var(--muted)">{new Date(`${m.date}T00:00:00Z`).toLocaleString("en-US", { month: "short", timeZone: "UTC" })}</text>)}
      {cells.map((c) => {
        const t = (c.value - lo) / (hi - lo || 1);
        return (
          <rect key={c.date} x={L + c.col * (S + G)} y={16 + c.row * (S + G)} width={S} height={S} rx={2.5}
            fill={`color-mix(in srgb, var(--accent) ${Math.round(10 + t * 80)}%, var(--surface))`}
            stroke={selected === c.date ? "var(--text)" : c.flag ? "var(--warn)" : "none"} strokeWidth={selected === c.date ? 2 : 1.5}
            {...act(onDay ? () => onDay(c.date) : undefined)} aria-label={`${c.date}: ${format(c.value)}${c.flag ? " (event)" : ""}`}>
            <title>{`${c.date}: ${format(c.value)}${c.flag ? " · event" : ""}`}</title>
          </rect>);
      })}
    </svg>
  );
}
