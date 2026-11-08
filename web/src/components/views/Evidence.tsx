"use client";
import { useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";

import { useApi } from "@/lib/api";
import { compact, n, pct, signed, usd } from "@/lib/format";
import type { EvidenceList, Forecast } from "@/lib/types";
import { useUI } from "@/lib/ui";

import { ErrorLine, EvidenceLink, Kpi, Loading, PageHead, Panel, Pill, Scroll, robustTone } from "../ui";

export function Evidence() {
  const ui = useUI();
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const qs = new URLSearchParams({ limit: "200", ...(q.trim() ? { q: q.trim() } : {}), ...(cat ? { category: cat } : {}) });
  const { data, error, reload } = useApi<EvidenceList>(`/evidence?${qs}`);
  const all = useApi<EvidenceList>("/evidence?limit=200");
  const cats = [...new Set((all.data?.data.claims ?? []).map((c) => String(c.category)))].sort();
  const d = data?.data;
  return (
    <div className="space-y-4">
      <PageHead title="Evidence" line="Every recommendation traces to a source, calculation and limitation." />
      {error && <ErrorLine error={error} retry={reload} />}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <Panel title={`Claims register${d ? ` · ${d.total}` : ""}`} flush right={
          <div className="flex flex-wrap gap-2">
            <label htmlFor="ev-q" className="sr-only">Search claims</label>
            <input id="ev-q" value={q} onChange={(e) => setQ(e.target.value)} maxLength={60} placeholder="Search" className="w-36 rounded border border-line bg-surface px-2 py-0.5 text-[12.5px]" />
            <label htmlFor="ev-cat" className="sr-only">Category</label>
            <select id="ev-cat" value={cat} onChange={(e) => setCat(e.target.value)} className="rounded border border-line bg-surface px-1.5 py-0.5 text-[12.5px]">
              <option value="">All categories</option>{cats.map((c) => <option key={c} value={c}>{c.replaceAll("_", " ")}</option>)}</select>
          </div>}>
          {!d ? <div className="p-4"><Loading rows={8} /></div> : (
            <div className="max-h-[640px] overflow-auto">
              <table className="tbl min-w-[980px]"><thead><tr><th>Claim</th><th>Source</th><th>Calculation</th><th>As of</th><th>Uncertainty</th><th>Limitation</th><th>Supports</th></tr></thead>
                <tbody>{d.claims.map((c) => (
                  <tr key={String(c.claim_id)} className="row-click" onClick={() => ui.openEvidence(String(c.claim_id))}>
                    <td className="text-[12.5px]"><span className="font-medium">{String(c.claim_text)}</span><div className="label">{String(c.claim_id)}</div></td>
                    <td className="text-[12px] text-muted">{String(c.source_table)}</td>
                    <td className="max-w-[220px] truncate text-[12px] text-muted" title={String(c.result)}>{String(c.result || "—")}</td>
                    <td className="num whitespace-nowrap text-[12px] text-muted">{String(c.data_as_of || "—")}</td>
                    <td><Pill tone={c.verification_status === "PASS" ? "pos" : c.evidence_classification === "RETRACTED" ? "neg" : "warn"}>{String(c.evidence_classification).replaceAll("_", " ").toLowerCase()}</Pill></td>
                    <td className="max-w-[260px] truncate text-[12px] text-muted" title={String(c.limitation)}>{String(c.limitation || "—")}</td>
                    <td className="text-[12px]">{String(c.decision)}</td></tr>))}</tbody></table>
              {d.claims.length === 0 && <p className="p-4 text-[13px] text-muted">No claims match; clear the search.</p>}
            </div>)}
        </Panel>
        <div className="space-y-4">
          {all.data && <>
            <Panel title="Decision passports" flush>
              <ul className="divide-y divide-line">{all.data.data.passports.map((p) => (
                <li key={String(p.passport_id)} className="flex items-center justify-between gap-2 px-4 py-2 text-[13px]">
                  <span className="min-w-0">{String(p.action_name)}<span className="label block">{String(p.portfolio_mode).replace("_", " ")} · {String(p.target_entity)}</span></span>
                  <EvidenceLink id={String(p.passport_id)}>Open</EvidenceLink></li>))}</ul>
            </Panel>
            <Panel title="Machine verdicts" note="Independently re-derived from raw data.">
              <ul className="space-y-1.5">{all.data.data.verification.map((v) => (
                <li key={String(v.machine_id)} className="flex items-center justify-between gap-2 text-[13px]">
                  <button type="button" onClick={() => ui.openEvidence(String(v.machine_id))} className="text-accent hover:underline">{String(v.machine_id)}</button>
                  <Pill tone={robustTone(String(v.classification))}>{String(v.classification).toLowerCase()}</Pill></li>))}</ul>
            </Panel>
            <Panel title="Evidence mix">
              <ul className="space-y-1">{Object.entries(all.data.data.classifications).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                <li key={k} className="flex justify-between text-[12.5px]"><span className="text-muted">{k.replaceAll("_", " ").toLowerCase()}</span><span className="num">{v}</span></li>))}</ul>
            </Panel>
          </>}
        </div>
      </div>
    </div>
  );
}

export function Validation() {
  const [marks, setMarks] = useState(true);
  const { data, error, reload } = useApi<Forecast>("/forecast/validation");
  if (error) return <ErrorLine error={error} retry={reload} />;
  if (!data) return <Loading rows={6} />;
  const d = data.data;
  const f = Object.fromEntries(d.comparison.map((x) => [String(x.subset), x]));
  const all = f.all, ev = f.event_days, ne = f.non_event_days;
  const p = d.protocol;
  const rows = d.holdout.map((r) => ({ d: String(r.gaming_date).slice(0, 10), actual: n(r.actual), model: n(r.candidate_pred), base: n(r.baseline_pred),
    band: [n(r.candidate_lo80), n(r.candidate_hi80)] as [number, number], evt: r.is_event_day ? n(r.actual) : null }));
  return (
    <div className="space-y-4">
      <PageHead title="Validation" line="Holt-Winters beats the baseline overall but not on promotion days." />
      <div className="panel flex flex-wrap gap-x-6 gap-y-2 p-4 text-[12.5px]">
        {[["Train", String(p.train)], ["Validate", String(p.validate)], ["Holdout", String(p.holdout)], ["Model", String(p.model)], ["Baseline", String(p.baseline)], ["Registry", String(p.registry)], ["Protocol", `${String(p.protocol_version)} · ${String(p.protocol_sha256).slice(0, 10)}…`]].map(([k, v]) => (
          <span key={k}><span className="label">{k} </span>{v}</span>))}
      </div>
      <div className="panel grid grid-cols-2 gap-4 p-4 lg:grid-cols-4">
        <Kpi label="Holdout MAE" value={usd(n(all?.candidate_mae))} sub={`baseline ${usd(n(all?.baseline_mae))} per day`} />
        <Kpi label="Improvement · all days" value={`${n(all?.mae_improvement_pct).toFixed(1)}%`} className="text-pos" sub={`non-event ${n(ne?.mae_improvement_pct).toFixed(1)}%`} />
        <Kpi label="Improvement · event days" value={`${n(ev?.mae_improvement_pct).toFixed(1)}%`} className="text-neg" sub={`${n(ev?.n)} days`} />
        <Kpi label="80% interval coverage" value={pct(n(all?.candidate_coverage80), 0)} className="text-warn" sub={`event days ${pct(n(ev?.candidate_coverage80), 0)}`} />
      </div>
      <Panel title="Actual vs forecast, daily floor theo" note="Black: actual · blue: Holt-Winters with 80% band · grey: baseline · amber: event days."
        right={<label className="label flex items-center gap-1"><input type="checkbox" checked={marks} onChange={(e) => setMarks(e.target.checked)} />Event days</label>}>
        <div className="h-64" role="img" aria-label="Holdout actual, model and baseline daily theo">
          <ResponsiveContainer><ComposedChart data={rows} margin={{ left: 0, right: 4 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="d" stroke="var(--muted)" fontSize={11} tickLine={false} axisLine={false} tickFormatter={(x: string) => x.slice(5)} minTickGap={24} />
            <YAxis stroke="var(--muted)" fontSize={11} tickLine={false} axisLine={false} width={52} tickFormatter={(x: number) => compact(x)} domain={["auto", "auto"]} />
            <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 12 }}
              formatter={(x, k) => [Array.isArray(x) ? `${usd(Number(x[0]))} – ${usd(Number(x[1]))}` : usd(Number(x)), String(k)]} />
            <Area isAnimationActive={false} dataKey="band" name="80% band" fill="var(--chart-1)" fillOpacity={0.1} stroke="none" />
            <Line isAnimationActive={false} dataKey="base" name="Baseline" stroke="var(--chart-2)" dot={false} strokeDasharray="3 3" />
            <Line isAnimationActive={false} dataKey="model" name="Holt-Winters" stroke="var(--chart-1)" dot={false} strokeWidth={1.75} />
            <Line isAnimationActive={false} dataKey="actual" name="Actual" stroke="var(--text)" dot={false} strokeWidth={1.25} />
            {marks && <Scatter isAnimationActive={false} dataKey="evt" name="Event day" fill="var(--chart-4)" />}
          </ComposedChart></ResponsiveContainer>
        </div>
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Error metrics" flush>
          <Scroll><table className="tbl min-w-[460px]"><thead><tr><th>Subset</th><th className="text-right">n</th><th className="text-right">MAE model / base</th><th className="text-right">RMSE model / base</th><th className="text-right">Bias</th><th className="text-right">Cov. 80%</th></tr></thead>
            <tbody>{d.comparison.map((x) => (
              <tr key={String(x.subset)}><td>{String(x.subset).replaceAll("_", " ")}</td><td className="num text-right">{String(x.n)}</td>
                <td className="num text-right">{compact(n(x.candidate_mae))} / {compact(n(x.baseline_mae))}</td>
                <td className="num text-right">{compact(n(x.candidate_rmse))} / {compact(n(x.baseline_rmse))}</td>
                <td className="num text-right">{signed(n(x.candidate_bias))}</td><td className="num text-right">{pct(n(x.candidate_coverage80), 0)}</td></tr>))}</tbody></table></Scroll>
          <p className="label border-t border-line px-4 py-2">Metrics differ slightly across SciPy/NumPy versions; recorded as a non-blocking gate.</p>
        </Panel>
        <Panel title="Which decision the model changes" note="Only the weak case; the model is weakest exactly there." flush>
          <Scroll><table className="tbl min-w-[460px]"><thead><tr><th>Counterfactual</th><th>Case</th><th className="text-right">Uplift / day</th><th>Plan</th><th className="text-right">Net</th></tr></thead>
            <tbody>{d.decision_impact.map((m, i) => (
              <tr key={i}><td className="text-[12.5px]">{String(m.counterfactual_method).replaceAll("_", " ")}</td><td className="text-[12.5px]">{String(m.statistic)}</td>
                <td className={`num text-right ${m.above_breakeven ? "" : "text-neg"}`}>{usd(n(m.a08_value))}</td>
                <td className="text-[12.5px]">{m.portfolio === "HOLD" ? "Hold" : "2 promotions"}</td><td className="num text-right">{signed(n(m.modeled_net))}</td></tr>))}</tbody></table></Scroll>
          <p className="label border-t border-line px-4 py-2">Model-driven change (keep promotions in the weak case) rated insufficient evidence.</p>
        </Panel>
      </div>
    </div>
  );
}
