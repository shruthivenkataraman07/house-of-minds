"use client";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useApi } from "@/lib/api";
import { OPTION, allocation, n, signed, tone, usd } from "@/lib/format";
import type { Portfolio, Portfolios, Scenarios as ScenarioData } from "@/lib/types";
import { useUI } from "@/lib/ui";

import { CompositionBar, ValueBars } from "../charts";
import { Drawer, ErrorLine, EvidenceLink, Kpi, Loading, PageHead, Panel, Pill, Scroll, Segmented, Tabs } from "../ui";

const SCEN: Record<string, string> = { zero_uplift: "Zero", weakest_event: "Weakest event", break_even: "Break-even",
  base_mean: "Base", strongest_event: "Strongest event" };
const ORDER = ["zero_uplift", "weakest_event", "break_even", "base_mean", "strongest_event"];
const OPTS = ["manager_proposal_lease", "house_of_minds_evidence", "house_of_minds_conditional", "house_of_minds_with_replacements_allowed", "no_action", "manager_proposal_buy"];

export function Scenarios() {
  const ui = useUI();
  const tab = ui.tab ?? "compare";
  const sc = useApi<ScenarioData>("/scenarios");
  const pf = useApi<Portfolios>("/portfolios");
  const [world, setWorld] = useState(ui.scenario ?? "base_mean");
  const [stressSel, setStressSel] = useState<string | null>(null);
  const err = sc.error ?? pf.error;
  if (err) return <ErrorLine error={err} retry={() => { sc.reload(); pf.reload(); }} />;
  if (!sc.data || !pf.data) return <Loading rows={6} />;
  const promo = sc.data.data.promotion;
  const s = promo.scenarios.find((x) => x.scenario === world)!;
  const options = pf.data.data.options;
  const byOpt = Object.fromEntries(options.map((o) => [o.option, o]));
  const evAlloc = byOpt.house_of_minds_evidence?.allocation;
  const cdAlloc = byOpt.house_of_minds_conditional?.allocation;
  const netIn = (p: Portfolio) => !p.feasible ? null : p.allocation === evAlloc ? s.original_evidence : p.allocation === cdAlloc ? s.original_conditional : p.expected_net_benefit_usd;

  return (
    <div className="space-y-4">
      <PageHead title="Scenarios" line="Compare July net benefit under alternative assumptions." />
      <Tabs label="Scenario view" value={tab} onChange={(t) => ui.set({ tab: t })} tabs={[
        { id: "compare", label: "Plans × uplift" }, { id: "stress", label: "Stress tests" }, { id: "reversals", label: "Decision flips" }]} />
      {tab === "compare" && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <span className="label">Promotion uplift</span>
            <Segmented label="Promotion uplift scenario" value={world} onChange={setWorld}
              options={ORDER.map((id) => ({ id, label: SCEN[id] }))} />
            <span className="label num">{usd(s.A08)}/day excess theo</span>
          </div>
          <Panel flush title="Plans under one assumption set" note={`All plans: ${pf.data.meta.decision_horizon}, same economics; promotion only affects plans that include it.`}>
            <Scroll><table className="tbl min-w-[820px]"><thead><tr><th>Plan</th><th>Actions</th><th className="text-right">Cost</th><th className="text-right">Contribution</th><th className="text-right">Net (selected)</th><th className="text-right">Downside</th><th>Feasible</th><th>Sensitive to</th><th /></tr></thead>
              <tbody>{OPTS.map((o) => byOpt[o]).filter(Boolean).map((p) => {
                const net = netIn(p);
                return (
                  <tr key={p.option}>
                    <td className="font-medium whitespace-nowrap">{OPTION[p.option] ?? p.option}{p.option === pf.data!.data.options.find((x) => x.option === "house_of_minds_evidence")?.option && <span className="ml-1.5"><Pill tone="accent">rec.</Pill></span>}</td>
                    <td className="text-[12.5px] text-muted">{allocation(p.allocation)}</td>
                    <td className="num text-right">{usd(p.cost_usd)}</td>
                    <td className="num text-right">{net === null ? "—" : usd(net + p.cost_usd)}</td>
                    <td className={`num text-right font-medium ${tone(net)}`}>{net === null ? "—" : signed(net)}</td>
                    <td className={`num text-right ${tone(p.net_low_usd)}`}>{p.net_low_usd === null || p.net_low_usd === p.net_high_usd ? "—" : signed(p.net_low_usd)}</td>
                    <td>{p.feasible ? <Pill tone="pos">yes</Pill> : <Pill tone="neg">over budget</Pill>}</td>
                    <td className="text-[12px] text-muted">{p.uncertainty_basis.startsWith("A08") ? "promotion uplift" : p.uncertainty_basis.startsWith("A10") ? "new-title capture" : p.allocation.includes("PROMO") ? "promotion uplift" : "—"}</td>
                    <td><EvidenceLink id={p.option} /></td>
                  </tr>);
              })}</tbody></table></Scroll>
          </Panel>
          <Panel title="At what promotion uplift does the recommendation stop paying?" note="Recommended plan net at each precomputed uplift case; dashed line = break-even. Select a point.">
            <div className="h-56" role="img" aria-label="Recommended plan net benefit versus promotion uplift">
              <ResponsiveContainer><LineChart data={[...promo.scenarios].sort((a, b) => a.A08 - b.A08).map((x) => ({ ...x, net: Math.round(x.original_evidence) }))} margin={{ left: 4, right: 16, top: 24, bottom: 8 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis type="number" dataKey="A08" domain={[0, "dataMax"]} stroke="var(--muted)" fontSize={11} tickLine={false} tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}K`} label={{ value: "Extra expected win per promotion day", position: "insideBottom", offset: -4, fontSize: 11, fill: "var(--muted)" }} height={40} />
                <YAxis stroke="var(--muted)" fontSize={11} tickLine={false} width={56} tickFormatter={(v: number) => `${v < 0 ? "−" : ""}$${Math.abs(v / 1000).toFixed(0)}K`} />
                <ReferenceLine y={0} stroke="var(--line-strong)" />
                <ReferenceLine x={promo.break_even_A08} stroke="var(--warn)" strokeDasharray="4 3" label={{ value: `break-even ${usd(promo.break_even_A08)}/day`, fontSize: 11, fill: "var(--warn)", position: "insideTopLeft" }} />
                <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 12 }} formatter={(v) => [signed(Number(v)), "Recommended plan net"]} labelFormatter={(v) => `${usd(Number(v))}/day uplift`} />
                <Line isAnimationActive={false} dataKey="net" stroke="var(--accent)" strokeWidth={2}
                  dot={(props: { cx?: number; cy?: number; payload?: { scenario: string } }) => <circle key={props.payload?.scenario} cx={props.cx} cy={props.cy} r={world === props.payload?.scenario ? 6 : 4} fill={world === props.payload?.scenario ? "var(--text)" : "var(--accent)"} style={{ cursor: "pointer" }} onClick={() => props.payload && setWorld(props.payload.scenario)} />} />
              </LineChart></ResponsiveContainer>
            </div>
            <p className="label mt-1">The plan’s net is linear in uplift; the weakest observed event ({usd(promo.a08.low)}/day) sits just below break-even. Two events, no control group.</p>
          </Panel>
          <p className="text-[13px]">At zero or weakest-event uplift the recommended plan loses to no action; the manager’s lease plan is negative throughout.</p>
        </>
      )}
      {tab === "stress" && (<>
        <Panel title="Which assumptions move the best achievable net most?" note={`Change in optimal July net vs the base conditional plan (${signed(byOpt.house_of_minds_conditional?.expected_net_benefit_usd)}). Select a bar.`}>
          <ValueBars label="Change in optimal net by stress scenario" format={signed} selected={stressSel}
            rows={[...sc.data.data.stress].map((r) => ({ r, d: n(r.optimal_net_benefit) - n(byOpt.house_of_minds_conditional?.expected_net_benefit_usd) }))
              .sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).map(({ r, d }) => ({
                key: String(r.scenario_id), label: String(r.description).slice(0, 34), value: Math.round(d), tone: d < 0 ? "neg" : d > 0 ? "pos" : "muted",
                note: r.baseline_still_optimal === "true" ? "baseline plan still optimal" : "plan changes", onClick: () => setStressSel(String(r.scenario_id)) }))} />
        </Panel>
        {stressSel && (() => {
          const r = sc.data!.data.stress.find((x) => x.scenario_id === stressSel)!;
          return (
            <Drawer label={`Scenario ${stressSel}`} onClose={() => setStressSel(null)} title={<><span className="label block">{String(r.scenario_kind).replaceAll("_", " ")}</span>{String(r.description)}</>}>
              <div className="grid grid-cols-2 gap-4">
                <Kpi label="Optimal July net" value={signed(n(r.optimal_net_benefit))} />
                <Kpi label="Regret of keeping baseline" value={usd(n(r.regret))} />
              </div>
              <p className="mt-4 text-[13px]"><span className="text-muted">Optimal plan: </span>{allocation(String(r.optimal_portfolio))}</p>
              <p className="mt-1 text-[13px]"><span className="text-muted">Baseline still optimal: </span>{r.baseline_still_optimal === "true" ? "yes" : "no"}</p>
              <p className="label mt-3">Source: dash_scenario_surface (Step 3 optimizer re-run). Values are modeled July contribution.</p>
            </Drawer>);
        })()}
        <Panel flush title="Optimizer re-run per stress scenario" note="Regret = loss from keeping the baseline plan.">
          <Scroll><table className="tbl min-w-[720px]"><thead><tr><th>Scenario</th><th>Optimal plan</th><th className="text-right">Optimal net</th><th className="text-right">Regret</th><th>Baseline holds</th></tr></thead>
            <tbody>{sc.data.data.stress.map((r) => (
              <tr key={String(r.scenario_id)}><td><span className="font-medium">{String(r.scenario_id)}</span><div className="label">{String(r.description)}</div></td>
                <td className="text-[12.5px]">{allocation(String(r.optimal_portfolio))}</td>
                <td className={`num text-right ${tone(n(r.optimal_net_benefit))}`}>{signed(n(r.optimal_net_benefit))}</td>
                <td className="num text-right">{usd(n(r.regret))}</td>
                <td>{r.baseline_still_optimal === "true" ? <Pill tone="pos">yes</Pill> : <Pill tone="warn">no</Pill>}</td></tr>))}</tbody></table></Scroll>
        </Panel></>
      )}
      {tab === "reversals" && (
        <Panel flush title="Assumption values that flip the chosen plan" note="Bisection boundaries from the Step 3 optimizer.">
          <Scroll><table className="tbl min-w-[720px]"><thead><tr><th>Assumption</th><th>Mode</th><th className="text-right">Flips at</th><th>From</th><th>To</th><th>Risk</th></tr></thead>
            <tbody>{sc.data.data.reversals.map((r) => (
              <tr key={String(r.scenario_id)}><td className="text-[12.5px]">{String(r.assumption_id)}</td><td className="text-[12.5px]">{String(r.mode)}</td>
                <td className="num text-right">{n(r.interval_low).toLocaleString("en-US", { maximumFractionDigits: n(r.interval_low) > 10 ? 0 : 3 })}</td>
                <td className="text-[12.5px]">{allocation(String(r.original_portfolio))}</td><td className="text-[12.5px]">{allocation(String(r.replacement_portfolio))}</td>
                <td><Pill tone={r.risk_class === "HIGH" ? "neg" : r.risk_class === "MEDIUM" ? "warn" : "muted"}>{String(r.risk_class).toLowerCase()}</Pill></td></tr>))}</tbody></table></Scroll>
        </Panel>
      )}
    </div>
  );
}

export function Investment() {
  const ui = useUI();
  const { data, error, reload } = useApi<Portfolios>("/portfolios");
  if (error) return <ErrorLine error={error} retry={reload} />;
  if (!data) return <Loading rows={6} />;
  const d = data.data;
  const ev = d.passports.filter((p) => p.portfolio_mode === "evidence_supported");
  const cd = d.passports.filter((p) => p.portfolio_mode === "conditional");
  const cost = ev.reduce((s, p) => s + n(p.total_cost), 0);
  const net = ev.reduce((s, p) => s + n(p.modeled_net_contribution), 0);
  const promo = d.promotion;
  const sc = Object.fromEntries(promo.scenarios.map((s) => [s.scenario, s]));
  const rec = d.options.find((o) => o.option === "house_of_minds_evidence");
  const noPromo = promo.reoptimised_promo_prohibited;
  const lead = Object.fromEntries(d.catalog.map((c) => [c.action_type_id, c.lead_days]));

  return (
    <div className="space-y-4">
      <PageHead title="Investment" line="Only evidence-supported actions qualify; the plan is conditional on promotion uplift." />
      <div className="panel grid grid-cols-2 gap-4 p-4 lg:grid-cols-4">
        <Kpi label="Spend" value={usd(cost)} sub="of $100,000" />
        <Kpi label="Modeled July net" value={signed(net)} className={tone(net)} />
        <Kpi label="Downside (weakest event)" value={signed(rec?.net_low_usd)} className={tone(rec?.net_low_usd)} />
        <Kpi label="Remaining budget" value={usd(100000 - cost)} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="How is the $100,000 used?" note="Recommended spend by action, and budget kept unused.">
          <CompositionBar label="Budget allocation" segments={[
            ...ev.map((p) => ({ key: String(p.passport_id), label: String(p.action_name), value: n(p.total_cost), display: usd(n(p.total_cost)), tone: "accent" as const, onClick: () => ui.openEvidence(String(p.passport_id)) })),
            { key: "unused", label: "Kept unused", value: 100000 - cost, display: usd(100000 - cost), tone: "muted" as const }]} />
          <p className="label mt-2">Conditional upside would add {usd(cd.filter((p) => p.action_type_id !== "A-PROMO").reduce((a, p) => a + n(p.total_cost), 0))} of inspection and moves.</p>
        </Panel>
        <Panel title="What does each action return?" note="Estimated additional net benefit per action (July). Select one for its passport.">
          <ValueBars label="Net benefit by action" format={signed}
            rows={[...ev, ...cd.filter((p) => p.action_type_id !== "A-PROMO")].map((p) => ({ key: String(p.passport_id), label: `${String(p.action_name).slice(0, 26)}${p.target_entity && p.target_entity !== "property weekend" ? ` · ${String(p.target_entity)}` : ""}`,
              value: n(p.modeled_net_contribution), tone: p.portfolio_mode === "evidence_supported" ? "accent" : "muted",
              note: `${usd(n(p.total_cost))} cost · ${String(p.portfolio_mode).replace("_", " ")}`, onClick: () => ui.openEvidence(String(p.passport_id)) }))} />
        </Panel>
      </div>
      <Panel title="Allocation worksheet" note="Lead time from the official action catalog; benefits accrue after it within Jul 1–30." flush>
        <Scroll><table className="tbl min-w-[820px]"><thead><tr><th>Action</th><th>Target</th><th>Mode</th><th className="text-right">Qty</th><th className="text-right" title="Catalog lead days before the action takes effect">Lead</th><th className="text-right">Cost</th><th className="text-right">Contribution</th><th className="text-right">Net</th><th>Basis</th><th /></tr></thead>
          <tbody>{[...ev, ...cd].map((p) => (
            <tr key={String(p.passport_id)} className={p.portfolio_mode === "conditional" ? "text-muted" : ""}>
              <td className="font-medium">{String(p.action_name)}</td><td className="text-[12.5px]">{String(p.target_entity)}</td>
              <td>{p.portfolio_mode === "evidence_supported" ? <Pill tone="accent">recommended</Pill> : <Pill>conditional</Pill>}</td>
              <td className="num text-right">{String(p.quantity)}</td>
              <td className="num text-right">{lead[String(p.action_type_id)] !== undefined ? `${lead[String(p.action_type_id)]} d` : "—"}</td>
              <td className="num text-right">{usd(n(p.total_cost))}</td>
              <td className="num text-right">{usd(n(p.modeled_incremental_effect))}</td>
              <td className={`num text-right ${tone(n(p.modeled_net_contribution))}`}>{signed(n(p.modeled_net_contribution))}</td>
              <td className="text-[12px]">{String(p.effect_classification).toLowerCase()}</td>
              <td><EvidenceLink id={String(p.passport_id)}>Passport</EvidenceLink></td></tr>))}</tbody></table></Scroll>
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Promotion robustness" note={`Break-even ${usd(promo.break_even_A08)}/day; ${promo.minus_1506_meaning.split(";")[1]?.trim() ?? "scenario values, not confidence bounds"}.`} flush>
          <Scroll><table className="tbl min-w-[420px]"><thead><tr><th>Uplift case</th><th className="text-right">$/day</th><th className="text-right">Recommended net</th><th className="text-right">Without promo</th></tr></thead>
            <tbody>{ORDER.map((k) => sc[k]).filter(Boolean).map((s) => (
              <tr key={s.scenario}><td>{SCEN[s.scenario]}</td><td className="num text-right">{usd(s.A08)}</td>
                <td className={`num text-right ${tone(Math.round(s.original_evidence))}`}>{signed(Math.round(s.original_evidence))}</td>
                <td className="num text-right">{signed(s.evidence_without_promo)}</td></tr>))}</tbody></table></Scroll>
          <p className="label border-t border-line px-4 py-2">Promotions prohibited: evidence mode holds ({signed(noPromo.evidence_supported?.net)}); conditional mode nets {signed(noPromo.conditional?.net)}. Two events, no control group.</p>
        </Panel>
        <Panel title="Constraints" flush>
          <ul className="divide-y divide-line">{d.constraints.map((c) => (
            <li key={c.check} className="flex items-start justify-between gap-3 px-4 py-2 text-[13px]">
              <span>{c.check}<span className="label block">{c.detail}</span></span>
              <Pill tone={c.pass ? "pos" : "neg"}>{c.pass ? "pass" : "fail"}</Pill></li>))}</ul>
        </Panel>
      </div>
      <Panel title="Measure in July" note="Step 5 measurement plans." flush>
        <Scroll><table className="tbl min-w-[760px]"><thead><tr><th>Action</th><th>Window</th><th>Success</th><th>Stop / revise</th></tr></thead>
          <tbody>{d.measurement_plans.map((m) => (
            <tr key={String(m.action_id)}><td className="font-medium whitespace-nowrap">{String(m.action_id)}</td><td className="text-[12.5px]">{String(m.observation_period)}</td>
              <td className="text-[12.5px]">{String(m.success_threshold)}</td>
              <td className="text-[12.5px]">{String(m.stop_or_revise)}{m.action_id === "A-PROMO" && <span className="mt-1 block text-warn">Not executable as written: weekend 2 must be ordered before weekend 1 is observed.</span>}</td></tr>))}</tbody></table></Scroll>
      </Panel>
      <Panel title="Not chosen" flush>
        <Scroll><table className="tbl min-w-[560px]"><thead><tr><th>Plan</th><th className="text-right">Cost</th><th className="text-right">Net</th><th>Reason</th></tr></thead>
          <tbody>{d.options.filter((o) => o.option !== "house_of_minds_evidence").map((o) => (
            <tr key={o.option}><td>{OPTION[o.option] ?? o.option}</td><td className="num text-right">{usd(o.cost_usd)}</td>
              <td className={`num text-right ${tone(o.expected_net_benefit_usd)}`}>{o.feasible ? signed(o.expected_net_benefit_usd) : "—"}</td>
              <td className="text-[12.5px] text-muted">{!o.feasible ? "Over the $100,000 budget." : o.option === "manager_proposal_lease" ? "Negative at every tested new-title value." : o.option === "no_action" ? "Safe baseline; forgoes modeled promotion return." : "Adds unmeasured planning assumptions."}</td></tr>))}</tbody></table></Scroll>
      </Panel>
    </div>
  );
}
