"use client";
import type { ReactNode } from "react";

import { GLOSSARY } from "@/lib/explain";
import { useUI } from "@/lib/ui";

import { Formula, type FormulaSpec } from "./math";
import { Drawer } from "./ui";

/** A term with a dotted underline; selecting it opens its plain-language definition. */
export function Term({ id, children }: { id: keyof typeof GLOSSARY; children?: ReactNode }) {
  const set = useUI((s) => s.set);
  const g = GLOSSARY[id];
  return (
    <button type="button" onClick={() => set({ glossary: id as string })} title={g.plain}
      className="cursor-help underline decoration-dotted decoration-1 underline-offset-[3px] hover:text-accent">
      {children ?? g.term}
    </button>
  );
}

/** "How this is calculated": numbered plain-language steps, technical detail last. */
export function How({ steps, technical, formulas, summary = "How this is calculated" }: { steps: ReactNode[]; technical?: ReactNode; formulas?: FormulaSpec[]; summary?: string }) {
  return (
    <details className="group mt-3 rounded-md border border-line bg-surface-2/60 text-[13.5px] leading-relaxed open:bg-surface-2">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 font-medium text-accent marker:hidden">
        <span aria-hidden className="inline-block transition-transform group-open:rotate-90">›</span>{summary}
      </summary>
      <div className="space-y-2 px-3 pb-3">
        <ol className="list-decimal space-y-1.5 pl-5 text-ink">{steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
        {formulas && formulas.length > 0 && <div className="space-y-2 pt-1">{formulas.map((f) => <Formula key={f.title} spec={f} />)}</div>}
        {technical && <p className="border-t border-line pt-2 text-[12.5px] text-muted"><span className="font-medium">For analysts: </span>{technical}</p>}
      </div>
    </details>
  );
}

/** Glossary drawer, opened from the header or from any Term. */
export function GlossaryDrawer() {
  const ui = useUI();
  if (!ui.glossary) return null;
  const focus = ui.glossary === "all" ? null : ui.glossary;
  const entries = Object.entries(GLOSSARY);
  return (
    <Drawer label="Glossary" onClose={() => ui.set({ glossary: null })} title={<><span className="label block">Plain-language glossary</span>What the numbers mean</>}>
      <dl className="space-y-4">
        {(focus ? [[focus, GLOSSARY[focus]] as const, ...entries.filter(([k]) => k !== focus)] : entries).map(([k, g]) => (
          <div key={k} className={k === focus ? "rounded-md bg-accent-soft p-3" : ""}>
            <dt className="text-[14px] font-semibold">{g.term}</dt>
            <dd className="mt-0.5 text-[13.5px] leading-relaxed">{g.plain}</dd>
            {g.example && <dd className="mt-1 text-[13px] text-muted">Example: {g.example}</dd>}
          </div>
        ))}
      </dl>
    </Drawer>
  );
}
