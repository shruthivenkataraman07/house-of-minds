"use client";
import { useState } from "react";

import { useApi } from "@/lib/api";
import { OPTION, allocation, signed, tone, usd, verdict } from "@/lib/format";
import type { Executive } from "@/lib/types";
import { useUI } from "@/lib/ui";

import { CompositionBar, type ChartTone, ValueBars } from "../charts";
import { ErrorLine, EvidenceLink, Kpi, Loading, Panel, Pill, Scroll, verdictTone } from "../ui";

const VTONE: Record<string, ChartTone> = { RETIRED_ALREADY: "muted", DO_NOT_REPLACE_INSPECT: "accent",
  DO_NOT_REPLACE_NOT_ECONOMIC: "neg", INSUFFICIENT_EVIDENCE: "warn", REPLACE_JUSTIFIED_CONDITIONAL: "pos", DO_NOT_REPLACE_EXPOSURE: "muted" };

const FACTOR: Record<string, string> = { exposure: "Limited floor time", location: "Weak location", game_config: "Low-edge game",
  luck: "Payout luck", machine_residual: "Machine itself" };

export function Overview() {
  const ui = useUI();
  const [cat, setCat] = useState<string | null>(null);
  const { data, error, loading, reload } = useApi<Executive>("/executive");
  if (loading && !data) return <Loading rows={6} />;
  if (error || !data) return <ErrorLine error={error} retry={reload} />;
  const x = data.data;
  const v = x.verdict;
  const pf = Object.fromEntries(x.portfolios.map((p) => [p.option, p]));
  const mgr = pf.manager_proposal_lease;
  const rec = pf[v.recommended_option];
  const diff = (rec?.expected_net_benefit_usd ?? 0) - (mgr?.expected_net_benefit_usd ?? 0);
  const offered = pf.house_of_minds_with_replacements_allowed;
  const picked = offered ? offered.allocation.split(";").filter((a) => a.includes("REPLACE")).length : null;
  const weak = x.promotion.scenarios.weakest_event;
  const order = ["manager_proposal_lease", "house_of_minds_evidence", "house_of_minds_conditional", "no_action", "manager_proposal_buy"];
  const factors = Object.entries(x.bottom10.reduce<Record<string, number>>((acc, m) => {
    (m.primary_factors ?? "").split(",").filter(Boolean).forEach((f) => { acc[f] = (acc[f] ?? 0) + 1; });
    return acc;
  }, {})).sort((a, b) => b[1] - a[1]);
  const vColor = v.answer === "REPLACE_NONE" ? "text-neg" : v.answer === "INSUFFICIENT_EVIDENCE" ? "text-warn" : "text-pos";

  return (
    <div className="space-y-4">
      <section className="panel p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-[15px] font-medium text-muted">Replace the bottom 10?</h1>
            <p className={`mt-0.5 text-[32px] font-semibold leading-tight tracking-tight ${vColor}`}>{verdict(v.answer)}</p>
            <p className="mt-1 text-[13px] text-muted">
              {v.replacement_justified} of {v.machines_reviewed} replacements justified{picked !== null && `; offered all, the optimizer chose ${picked === 0 ? "none" : picked}`}.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => ui.go("machines")} className="rounded-md bg-accent px-3 py-1.5 text-[13px] font-medium text-white hover:opacity-90">Investigate machines</button>
            <button type="button" onClick={() => ui.go("scenarios")} className="rounded-md border border-line bg-surface px-3 py-1.5 text-[13px] hover:border-line-strong">Compare plans</button>
            <button type="button" onClick={() => ui.go("evidence")} className="rounded-md border border-line bg-surface px-3 py-1.5 text-[13px] hover:border-line-strong">View evidence</button>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-4 border-t border-line pt-4 md:grid-cols-3 xl:grid-cols-6">
          <Kpi label="Manager plan · July net" value={signed(mgr?.expected_net_benefit_usd)} className={tone(mgr?.expected_net_benefit_usd)} sub={`${usd(mgr?.cost_usd)} to lease ${x.bottom10.filter((m) => m.verdict !== "RETIRED_ALREADY").length}`} />
          <Kpi label="Recommended · July net" value={signed(rec?.expected_net_benefit_usd)} className={tone(rec?.expected_net_benefit_usd)} sub={allocation(rec?.allocation)} />
          <Kpi label="Difference" value={signed(diff)} className={tone(diff)} sub="same horizon and definitions" />
          <Kpi label="Spend" value={usd(rec?.cost_usd)} sub={`${usd(rec?.remaining_budget_usd)} of $100,000 kept`} />
          <Kpi label="Alternative candidates" value={`${x.floor_planning_positive} / ${x.floor_candidates}`} sub={`pay back at planning value; ${x.floor_best_case_positive} only in best case`} title="Floor-wide lease replacement candidates" />
          <Kpi label="Key uncertainty" value={`${usd(x.promotion.break_even)}/day`} className="text-warn" sub={`promotion break-even; weakest event → ${signed(weak)}`} />
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="What does each plan return in July?" note="Estimated additional net benefit; whiskers show the tested assumption range.">
          <ValueBars label="Modeled July net benefit by plan" format={signed} selected={v.recommended_option}
            rows={order.filter((o) => pf[o]).map((o) => {
              const p = pf[o];
              return { key: o, label: OPTION[o] ?? o, value: p.feasible ? p.expected_net_benefit_usd : null,
                low: p.net_low_usd, high: p.net_high_usd, note: p.feasible ? `${usd(p.cost_usd)} spent` : "over the $100,000 budget",
                tone: !p.feasible ? "muted" : o === v.recommended_option ? "accent" : (p.expected_net_benefit_usd ?? 0) < 0 ? "neg" : "muted",
                onClick: () => ui.openEvidence(o) };
            })} />
          <p className="label mt-1">Select a plan to open its evidence passport.</p>
        </Panel>
        <Panel title="How are the manager’s 10 classified?" note="Select a category to see its machines and evidence.">
          {(() => {
            const counts = x.bottom10.reduce<Record<string, number>>((a, m) => ({ ...a, [m.verdict]: (a[m.verdict] ?? 0) + 1 }), {});
            const sel = cat ?? Object.keys(counts)[0];
            return (
              <>
                <CompositionBar label="Manager's 10 by verdict" selected={sel}
                  segments={Object.entries(counts).map(([k, c]) => ({ key: k, label: verdict(k), value: c, tone: VTONE[k] ?? "muted", onClick: () => setCat(k) }))} />
                <ul className="mt-3 divide-y divide-line border-t border-line">
                  {x.bottom10.filter((m) => m.verdict === sel).map((m) => (
                    <li key={m.machine_id} className="flex items-center justify-between gap-3 py-1.5 text-[12.5px]">
                      <button type="button" onClick={() => ui.go("machines", { machineId: m.machine_id })} className="font-medium text-accent hover:underline">{m.machine_id}</button>
                      <span className="min-w-0 flex-1 truncate text-muted">{m.recommended_alternative}</span>
                      <EvidenceLink id={m.machine_id} />
                    </li>))}
                </ul>
                <p className="label mt-2">Proposed for replacement: {x.bottom10.length} · supported: {v.replacement_justified} · floor-wide candidates paying back at planning value: {x.floor_planning_positive} of {x.floor_candidates}.</p>
              </>);
          })()}
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Panel title="Why the ranking changes" note="Lowest earnings ≠ weakest machine: compare earnings rank with fair rank and floor time." flush
          right={<button type="button" onClick={() => ui.go("machines")} className="text-[12.5px] text-accent hover:underline">All machines →</button>}>
          <Scroll>
            <table className="tbl min-w-[680px]">
              <thead><tr><th className="text-right" title="Manager's rank by total house win (1 = lowest)">Earnings #</th><th>Machine</th><th className="text-right">House win</th><th className="text-right" title="Rank vs same-game peers on expected win per available hour; 1 = weakest, 310 = strongest">Fair rank</th><th className="text-right">Days on floor</th><th>Verdict</th><th>Main reason</th></tr></thead>
              <tbody>{x.bottom10.map((m) => (
                <tr key={m.machine_id} className="row-click" onClick={() => ui.go("machines", { machineId: m.machine_id })}>
                  <td className="num text-right text-muted">{m.manager_rank}</td>
                  <td className="whitespace-nowrap font-medium">{m.machine_id}</td>
                  <td className="num text-right">{usd(m.house_win_usd)}</td>
                  <td className="num text-right">{m.rank_vs_peers}<span className="label"> /310</span></td>
                  <td className={`num text-right ${m.active_days < 150 ? "text-warn" : ""}`}>{m.active_days}</td>
                  <td><Pill tone={verdictTone(m.verdict)}>{verdict(m.verdict)}</Pill></td>
                  <td className="text-[12.5px] text-muted">{m.verdict === "RETIRED_ALREADY" ? `Retired ${m.retire_date}` : m.verdict === "DO_NOT_REPLACE_INSPECT" ? `Payout fault (hit-rate z ${m.hit_rate_z.toFixed(0)})` : m.verdict === "INSUFFICIENT_EVIDENCE" ? `Best-case lease ${signed(m.lease_net_best_case_usd)}` : `Lease loses ${usd(-(m.lease_net_best_case_usd ?? 0))} even at best`}</td>
                </tr>))}</tbody>
            </table>
          </Scroll>
        </Panel>
        <div className="space-y-4">
          <Panel title="Top decision factors" note="Primary drivers of the earnings gap across the 10.">
            <ul className="space-y-2">{factors.map(([f, c]) => (
              <li key={f} className="grid grid-cols-[minmax(0,1fr)_88px_24px] items-center gap-2 text-[12.5px]">
                <span>{FACTOR[f] ?? f}</span>
                <span className="h-1.5 rounded bg-surface-2"><span className="block h-1.5 rounded bg-accent/70" style={{ width: `${c * 10}%` }} /></span>
                <span className="num text-right text-muted">{c}</span>
              </li>))}</ul>
            <p className="label mt-3 border-t border-line pt-2">Council matched {v.council_agreement}/10 verdicts; {x.council_verified}/{x.council_claims} claims verified.</p>
          </Panel>
          <Panel title="Evidence">
            <ul className="space-y-1.5 text-[12.5px]">
              {(["RETIRED_ALREADY", "DO_NOT_REPLACE_INSPECT", "DO_NOT_REPLACE_NOT_ECONOMIC", "INSUFFICIENT_EVIDENCE"] as const).map((k) => {
                const m = x.bottom10.find((b) => b.verdict === k);
                const count = x.bottom10.filter((b) => b.verdict === k).length;
                return m ? <li key={k} className="flex justify-between gap-2"><span>{count} × {verdict(k).toLowerCase()}</span><EvidenceLink id={m.machine_id}>{m.machine_id}</EvidenceLink></li> : null;
              })}
            </ul>
          </Panel>
        </div>
      </div>

      <Panel title="Plans compared" note={`Modeled net contribution, ${data.meta.decision_horizon}.`} flush>
        <Scroll>
          <table className="tbl min-w-[640px]">
            <thead><tr><th>Plan</th><th>Actions</th><th className="text-right">Cost</th><th className="text-right">Net</th><th className="text-right">Tested range</th><th /></tr></thead>
            <tbody>{order.map((o) => pf[o]).filter(Boolean).map((p) => (
              <tr key={p.option}>
                <td className="font-medium whitespace-nowrap">{OPTION[p.option] ?? p.option}{p.option === v.recommended_option && <span className="ml-1.5"><Pill tone="accent">recommended</Pill></span>}</td>
                <td className="text-[12.5px] text-muted">{allocation(p.allocation)}</td>
                <td className="num text-right">{usd(p.cost_usd)}</td>
                <td className={`num text-right font-medium ${tone(p.expected_net_benefit_usd)}`}>{p.feasible ? signed(p.expected_net_benefit_usd) : <Pill tone="neg">over budget</Pill>}</td>
                <td className="num text-right text-[12.5px] text-muted">{p.net_low_usd !== null && p.net_low_usd !== p.net_high_usd ? `${signed(p.net_low_usd)} to ${signed(p.net_high_usd)}` : "—"}</td>
                <td className="text-right"><EvidenceLink id={p.option} /></td>
              </tr>))}</tbody>
          </table>
        </Scroll>
      </Panel>
    </div>
  );
}
