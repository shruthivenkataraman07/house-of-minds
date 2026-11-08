"use client";
import { type ReactNode, useEffect, useRef, useState } from "react";

import type { ApiError } from "@/lib/api";
import { useUI } from "@/lib/ui";

/** One color per meaning. Verdict categories have their own tones so no hue means two things. */
export type Tone = "pos" | "neg" | "warn" | "accent" | "muted" | "insufficient" | "inspect" | "retired" | "conditional";
const PILL: Record<Tone, string> = {
  pos: "text-pos bg-pos/10", neg: "text-neg bg-neg/10", warn: "text-warn bg-warn/10",
  accent: "text-accent bg-accent-soft", muted: "text-muted bg-surface-2",
  insufficient: "text-insufficient bg-insufficient/10", inspect: "text-inspect bg-inspect/10",
  retired: "text-muted bg-surface-2", conditional: "text-accent bg-conditional/15",
};

export function Pill({ tone = "muted", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return <span title={title} className={`inline-flex items-center rounded px-1.5 py-0.5 text-[12px] font-medium leading-tight whitespace-nowrap ${PILL[tone]}`}>{children}</span>;
}

export const VERDICT_TONE: Record<string, Tone> = {
  REPLACE_JUSTIFIED_CONDITIONAL: "pos", INSUFFICIENT_EVIDENCE: "insufficient", DO_NOT_REPLACE_INSPECT: "inspect",
  RETIRED_ALREADY: "retired", DO_NOT_REPLACE_NOT_ECONOMIC: "neg", DO_NOT_REPLACE_EXPOSURE: "retired",
};
export const verdictTone = (v: string | null | undefined): Tone => (v ? VERDICT_TONE[v] ?? "neg" : "muted");
export const robustTone = (v: string | null | undefined): Tone =>
  v === "ROBUST" || v === "VERIFIED" ? "pos" : v === "CONDITIONAL" || v === "VERIFIED WITH ASSUMPTIONS" ? "warn" : v ? "neg" : "muted";

export function Panel({ title, note, right, children, className = "", flush = false }: {
  title?: ReactNode; note?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; flush?: boolean }) {
  return (
    <section className={`panel ${className}`}>
      {(title || right) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
          <div className="min-w-0"><h2 className="text-[14px] font-semibold leading-snug">{title}</h2>{note && <p className="label mt-0.5">{note}</p>}</div>
          {right}
        </header>
      )}
      <div className={flush ? "" : "p-4"}>{children}</div>
    </section>
  );
}

export function Kpi({ label, value, sub, className = "", title }: { label: ReactNode; value: ReactNode; sub?: ReactNode; className?: string; title?: string }) {
  return (
    <div className="min-w-0" title={title}>
      <p className="label">{label}</p>
      <p className={`num mt-1 text-[22px] font-semibold leading-tight tracking-[-0.02em] ${className}`}>{value}</p>
      {sub && <p className="label mt-0.5">{sub}</p>}
    </div>
  );
}

export function EvidenceLink({ id, children }: { id: string; children?: ReactNode }) {
  const open = useUI((s) => s.openEvidence);
  return (
    <button type="button" onClick={() => open(id)} className="whitespace-nowrap text-[12px] text-accent hover:underline" aria-label={`Open evidence ${id}`}>
      {children ?? "Evidence"} ↗
    </button>
  );
}

export function Tabs({ tabs, value, onChange, label }: { tabs: { id: string; label: string }[]; value: string; onChange: (id: string) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-0.5 border-b border-line">
      {tabs.map((t) => (
        <button key={t.id} role="tab" type="button" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={`-mb-px border-b-2 px-3 py-2 text-[13px] ${value === t.id ? "border-accent font-medium text-ink" : "border-transparent text-muted hover:text-ink"}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Segmented({ options, value, onChange, label }: { options: { id: string; label: string }[]; value: string; onChange: (id: string) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap rounded-md border border-line bg-surface p-0.5">
      {options.map((o) => (
        <button key={o.id} type="button" role="radio" aria-checked={value === o.id} onClick={() => onChange(o.id)}
          className={`rounded px-2.5 py-1 text-[12.5px] ${value === o.id ? "bg-surface-2 font-medium text-ink shadow-[inset_0_0_0_1px_var(--line)]" : "text-muted hover:text-ink"}`}>{o.label}</button>
      ))}
    </div>
  );
}

/** Page title, then its answer: the takeaway is the most prominent text after the title. */
export function PageHead({ title, line, right }: { title: string; line?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0 max-w-[820px]"><h1 className="text-[14px] font-medium text-muted">{title}</h1>{line && <p className="mt-1 text-[20px] font-semibold leading-snug tracking-[-0.01em] text-balance text-ink sm:text-[22px]">{line}</p>}</div>
      {right}
    </div>
  );
}

/** Skeleton rows; after 2.5 s explains the free host's cold start instead of looking broken. */
export function Loading({ rows = 3 }: { rows?: number }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => { const t = setTimeout(() => setSlow(true), 2500); return () => clearTimeout(t); }, []);
  return (
    <div aria-busy="true" aria-label="Loading" className="space-y-2">
      {slow && <p role="status" className="rise flex items-center gap-2 text-[13px] text-muted"><span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />Waking the House: the free host sleeps when idle, so the first load can take up to 30 seconds.</p>}
      {Array.from({ length: rows }, (_, i) => <div key={i} className="h-9 animate-pulse rounded bg-surface-2" />)}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-dashed border-line px-3 py-6 text-center text-[13px] text-muted">{children}</p>;
}

export function ErrorLine({ error, retry }: { error?: ApiError; retry?: () => void }) {
  return (
    <p role="alert" className="flex flex-wrap items-center gap-2 rounded border border-neg/30 bg-neg/5 px-3 py-2 text-[13px] text-neg">
      {error?.detail ?? "Request failed."} <span className="text-muted">{error?.recovery}</span>
      {retry && <button type="button" onClick={retry} className="text-accent underline">Retry</button>}
    </p>
  );
}

export function Drawer({ title, onClose, children, label }: { title: ReactNode; onClose: () => void; children: ReactNode; label: string }) {
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/20" onClick={onClose} role="presentation">
      <aside role="dialog" aria-modal="true" aria-label={label} onClick={(e) => e.stopPropagation()}
        className="flex h-full w-full max-w-[520px] flex-col border-l border-line bg-surface shadow-xl">
        <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0 text-[14px] font-semibold">{title}</div>
          <button type="button" onClick={onClose} className="rounded px-1.5 text-muted hover:text-ink" aria-label="Close">✕</button>
        </header>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
      </aside>
    </div>
  );
}

/** Horizontal scroll for wide tables, with an edge fade while more columns are hidden. */
export function Scroll({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [more, setMore] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => setMore(el.scrollWidth - el.clientWidth - el.scrollLeft > 4);
    check();
    el.addEventListener("scroll", check, { passive: true });
    const ro = new ResizeObserver(check); ro.observe(el);
    return () => { el.removeEventListener("scroll", check); ro.disconnect(); };
  }, []);
  return (
    <div className="scroll-x" data-more={more}>
      <div ref={ref} className="scroll-body" tabIndex={more ? 0 : undefined} role={more ? "region" : undefined} aria-label={more ? "Scrollable table" : undefined}>{children}</div>
      {more && <p className="label px-4 py-1.5 sm:hidden" aria-hidden>Swipe for more columns →</p>}
    </div>
  );
}
