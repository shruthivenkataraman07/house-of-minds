"use client";
import type { ReactNode } from "react";

import type { ApiError } from "@/lib/api";
import { useUI } from "@/lib/ui";

export type Tone = "pos" | "neg" | "warn" | "accent" | "muted";
const PILL: Record<Tone, string> = {
  pos: "text-pos bg-pos/10", neg: "text-neg bg-neg/10", warn: "text-warn bg-warn/10",
  accent: "text-accent bg-accent-soft", muted: "text-muted bg-surface-2",
};

export function Pill({ tone = "muted", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return <span title={title} className={`inline-flex items-center rounded px-1.5 py-px text-[11.5px] font-medium whitespace-nowrap ${PILL[tone]}`}>{children}</span>;
}

export const verdictTone = (v: string | null | undefined): Tone =>
  v === "REPLACE_JUSTIFIED_CONDITIONAL" ? "pos" : v === "INSUFFICIENT_EVIDENCE" ? "warn"
    : v === "DO_NOT_REPLACE_INSPECT" ? "accent" : v === "RETIRED_ALREADY" ? "muted" : v ? "neg" : "muted";
export const robustTone = (v: string | null | undefined): Tone =>
  v === "ROBUST" || v === "VERIFIED" ? "pos" : v === "CONDITIONAL" || v === "VERIFIED WITH ASSUMPTIONS" ? "warn" : v ? "neg" : "muted";

export function Panel({ title, note, right, children, className = "", flush = false }: {
  title?: ReactNode; note?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; flush?: boolean }) {
  return (
    <section className={`panel ${className}`}>
      {(title || right) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <div className="min-w-0"><h2 className="text-[13px] font-semibold">{title}</h2>{note && <p className="label mt-0.5">{note}</p>}</div>
          {right}
        </header>
      )}
      <div className={flush ? "" : "p-4"}>{children}</div>
    </section>
  );
}

export function Kpi({ label, value, sub, className = "", title }: { label: string; value: ReactNode; sub?: ReactNode; className?: string; title?: string }) {
  return (
    <div className="min-w-0" title={title}>
      <p className="label">{label}</p>
      <p className={`num mt-0.5 text-[22px] font-semibold leading-tight tracking-tight ${className}`}>{value}</p>
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

export function PageHead({ title, line, right }: { title: string; line?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0"><h1 className="text-[20px] font-semibold tracking-tight">{title}</h1>{line && <p className="mt-0.5 text-[13px] text-muted">{line}</p>}</div>
      {right}
    </div>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return <div aria-busy="true" aria-label="Loading" className="space-y-2">{Array.from({ length: rows }, (_, i) => <div key={i} className="h-9 animate-pulse rounded bg-surface-2" />)}</div>;
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

export function Scroll({ children }: { children: ReactNode }) {
  return <div className="overflow-x-auto">{children}</div>;
}
