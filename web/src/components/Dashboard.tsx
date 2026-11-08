"use client";
import { useEffect, useRef, useState } from "react";

import { postJSON, useApi } from "@/lib/api";
import type { AskAnswer, Metadata, Passport } from "@/lib/types";
import { OFFICIAL, VIEWS, type ViewId, useUI } from "@/lib/ui";

import { Drawer, EvidenceLink, ErrorLine, Loading, Pill } from "./ui";
import { Answers } from "./views/Answers";
import { Overview } from "./views/CommandCenter";
import { Council } from "./views/Council";
import { Investment, Scenarios } from "./views/Decisions";
import { Evidence, Validation } from "./views/Evidence";
import { Machines } from "./views/Machines";
import { Operations } from "./views/Operations";

const PAGES: Record<ViewId, () => React.JSX.Element> = {
  overview: Overview, machines: Machines, operations: Operations, council: Council,
  scenarios: Scenarios, investment: Investment, evidence: Evidence, validation: Validation,
  answers: Answers,
};

export default function Dashboard() {
  const ui = useUI();
  const meta = useMetadata();
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const sync = (initial: boolean) => {
      const h = window.location.hash.slice(1) as ViewId;
      if (!VIEWS.some((v) => v.id === h) || useUI.getState().view === h) return;
      if (initial) useUI.setState({ view: h }); else useUI.getState().go(h);
    };
    sync(true);
    const onHash = () => sync(false);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    mainRef.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
    // push a history entry per view so browser Back/Forward move between views; selections live in the store
    if (window.location.hash.slice(1) !== ui.view) {
      if (window.location.hash) window.history.pushState(null, "", `#${ui.view}`);
      else window.history.replaceState(null, "", `#${ui.view}`);
    }
  }, [ui.view]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); useUI.getState().set({ askOpen: true }); }
      if (e.key === "/" && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLTextAreaElement)) { e.preventDefault(); useUI.getState().set({ askOpen: true }); }
      if (e.key === "Escape") useUI.getState().set({ askOpen: false, evidenceId: null });
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);

  const Page = PAGES[ui.view];
  const current = VIEWS.find((v) => v.id === ui.view)?.label;
  const exploratory = ui.period.from !== OFFICIAL.from || ui.period.to !== OFFICIAL.to;

  return (
    <div className="min-h-screen md:grid md:grid-cols-[184px_minmax(0,1fr)]">
      <aside className="border-line bg-surface md:sticky md:top-0 md:h-screen md:border-r">
        <div className="px-4 py-3">
          <button type="button" onClick={() => ui.go("overview")} className="text-left">
            <span className="block text-[13px] font-semibold tracking-tight">House of Minds</span>
            <span className="label block">Gilded Ace decision system</span>
          </button>
        </div>
        <nav aria-label="Primary" className="overflow-x-auto border-b border-line md:border-0">
          <ul className="flex gap-0.5 px-2 pb-2 md:flex-col">
            {VIEWS.map((v) => (
              <li key={v.id}>
                <button type="button" onClick={() => ui.go(v.id)} aria-current={ui.view === v.id ? "page" : undefined}
                  className={`w-full whitespace-nowrap rounded-md px-2.5 py-1.5 text-left text-[13px] ${ui.view === v.id ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-surface-2 hover:text-ink"}`}>
                  {v.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line bg-bg/95 px-4 py-2 backdrop-blur-sm sm:px-6">
          <span className="text-[13px] font-medium">{current}</span>
          <span className="label hidden sm:inline">Official window Jan 1–Jun 30, 2025</span>
          {exploratory && <Pill tone="warn">Exploratory {ui.period.from} → {ui.period.to}</Pill>}
          <span className="ml-auto flex items-center gap-2">
            {meta && <span title={`${meta.note}; exported ${meta.exported_at_utc}; ${meta.verified_files} files verified`}>
              <Pill tone={meta.live ? "pos" : "muted"}>{meta.live ? "Live · Databricks" : "Validated snapshot"}</Pill></span>}
            {meta && <span className="label hidden lg:inline">as of {meta.exported_at_utc.slice(0, 10)}</span>}
            {ui.history.length > 0 && <button type="button" onClick={ui.back} className="rounded-md border border-line bg-surface px-2 py-1 text-[12.5px] text-muted hover:text-ink" aria-label="Back to previous view">← Back</button>}
            <button type="button" onClick={() => ui.set({ askOpen: true })} aria-haspopup="dialog"
              className="flex items-center gap-2 rounded-md border border-line bg-surface px-2.5 py-1 text-[12.5px] text-muted hover:border-line-strong hover:text-ink">
              Ask the House <kbd className="hidden rounded border border-line px-1 text-[10.5px] sm:inline">⌘K</kbd>
            </button>
          </span>
        </header>
        <main ref={mainRef} tabIndex={-1} className="mx-auto max-w-[1280px] px-4 py-5 sm:px-6">
          <Page key={ui.view} />
        </main>
        <footer className="label mx-auto max-w-[1280px] px-4 pb-8 sm:px-6">
          {meta ? `Snapshot ${meta.snapshot_id} · ${meta.note}` : "Loading snapshot…"} · Modeled values are July contribution, not realized profit · Agents are rule-based.
        </footer>
      </div>
      {ui.evidenceId && <EvidenceDrawer id={ui.evidenceId} />}
      {ui.askOpen && <AskPalette />}
    </div>
  );
}

function useMetadata(): Metadata | null {
  const [m, setM] = useState<Metadata | null>(null);
  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_BASE ?? ""}/api/v1/metadata`).then((r) => r.json()).then(setM, () => setM(null));
  }, []);
  return m;
}

function EvidenceDrawer({ id }: { id: string }) {
  const ui = useUI();
  const { data, error, loading, reload } = useApi<Passport>(`/evidence/${encodeURIComponent(id)}`);
  const p = data?.data;
  return (
    <Drawer label="Evidence passport" onClose={ui.back} title={<><span className="label block">Evidence passport · {p?.kind ?? "…"}</span>{p?.title ?? id}</>}>
      {loading && <Loading rows={6} />}
      {error && <ErrorLine error={error} retry={reload} />}
      {p && (
        <>
          <dl className="grid grid-cols-[minmax(0,1fr)] gap-x-4 gap-y-2.5 sm:grid-cols-[110px_minmax(0,1fr)]">
            {p.fields.map(([k, v], i) => (
              <div key={i} className="contents"><dt className="label pt-px">{k}</dt>
                <dd className={`text-[13px] [overflow-wrap:anywhere] ${v.includes("not recorded") ? "italic text-muted" : ""}`}>{v}</dd></div>
            ))}
          </dl>
          {p.links.length > 0 && <div className="mt-4 flex flex-wrap gap-x-3 gap-y-1 border-t border-line pt-3"><span className="label">Linked</span>{p.links.map((l) => <EvidenceLink key={l} id={l}>{l}</EvidenceLink>)}</div>}
          <p className="label mt-4">Source {data?.meta.served_from} · snapshot {data?.meta.snapshot_id}</p>
          <button type="button" onClick={ui.back} className="mt-3 rounded-md border border-line px-2.5 py-1 text-[12.5px] hover:border-line-strong">← Return to previous view</button>
        </>
      )}
    </Drawer>
  );
}

const SUGGEST = ["Why not replace the bottom 10?", "Explain machine M-5076", "Compare the manager's plan with House of Minds",
  "What if promotion uplift is zero?", "Why did the council challenge this?", "How reliable is the forecast?",
  "Which machines are affected by downtime?", "Show the six answers"];

function AskPalette() {
  const ui = useUI();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<{ q: string; a?: AskAnswer; err?: string } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current?.focus(); }, []);
  const close = () => ui.set({ askOpen: false });

  const submit = async (text: string) => {
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      const a = await postJSON<AskAnswer>("/ask", { question: text.slice(0, 400), machine_context: ui.machineId ?? undefined });
      setRes({ q: text, a });
    } catch (e) {
      setRes({ q: text, err: (e as Error).message || "Request failed; check the API is running." });
    } finally { setBusy(false); }
  };
  const run = (a: AskAnswer) => {
    if (!a.action) return;
    const { view, args } = a.action;
    if (args.evidence_id) { ui.set({ askOpen: false }); ui.openEvidence(args.evidence_id); return; }
    ui.go(view as ViewId, { machineId: args.machine_id ?? ui.machineId, zoneId: args.zone_id ?? ui.zoneId,
      bankId: args.bank_id ?? ui.bankId, tab: args.tab ?? null, scenario: args.scenario ?? ui.scenario, askOpen: false,
      ...(args.start && args.end ? { period: { from: args.start, to: args.end } } : {}) });
  };
  const toneOf = { OK: "pos", UNAVAILABLE: "warn", AMBIGUOUS: "warn", UNSUPPORTED: "muted", REFUSED: "neg" } as const;
  const a = res?.a;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/25 px-3 pt-[12vh]" onClick={close} role="presentation">
      <div role="dialog" aria-modal="true" aria-label="Ask the House" onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[640px] overflow-hidden rounded-lg border border-line bg-surface shadow-2xl">
        <form onSubmit={(e) => { e.preventDefault(); void submit(q); }} className="flex items-center gap-2 border-b border-line px-3">
          <label htmlFor="ask-input" className="sr-only">Ask the House</label>
          <input id="ask-input" ref={input} value={q} onChange={(e) => setQ(e.target.value)} maxLength={400}
            placeholder="Ask about a machine, plan, council check or forecast…" className="min-w-0 flex-1 bg-transparent py-3 text-[14px] outline-none" />
          <button type="submit" disabled={busy} className="rounded bg-accent px-2.5 py-1 text-[12.5px] font-medium text-white disabled:opacity-50">{busy ? "…" : "Ask"}</button>
        </form>
        <div className="max-h-[56vh] overflow-y-auto p-3" aria-live="polite">
          {!res && (
            <ul>{SUGGEST.map((s) => <li key={s}><button type="button" onClick={() => { setQ(s); void submit(s); }} className="w-full rounded px-2 py-1.5 text-left text-[13px] text-muted hover:bg-surface-2 hover:text-ink">{s}</button></li>)}</ul>
          )}
          {res?.err && <p role="alert" className="text-[13px] text-neg">{res.err} <span className="text-muted">Retry, or use the sidebar.</span></p>}
          {a && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-1.5"><Pill tone={toneOf[a.status]}>{a.status}</Pill><span className="label">{a.intent} · {a.period}</span></div>
              {a.premise_correction && <p className="text-[13px] text-warn">{a.premise_correction}</p>}
              <p className="text-[14px]">{a.conclusion}</p>
              {a.support.length > 0 && <ul className="list-disc space-y-0.5 pl-5 text-[12.5px] text-muted">{a.support.map((s, i) => <li key={i}>{s}</li>)}</ul>}
              {a.uncertainty && <p className="text-[12.5px] text-warn">{a.uncertainty}</p>}
              <div className="flex flex-wrap items-center gap-3 pt-1">
                {a.action && <button type="button" onClick={() => run(a)} className="rounded border border-accent/40 px-2 py-1 text-[12.5px] text-accent hover:bg-accent-soft">Open {a.action.view} →</button>}
                {a.evidence && <span className="label">Source: {a.evidence}</span>}
              </div>
            </div>
          )}
        </div>
        <p className="label border-t border-line px-3 py-2">Deterministic router via POST /api/v1/ask · read-only · no SQL, no LLM</p>
      </div>
    </div>
  );
}
