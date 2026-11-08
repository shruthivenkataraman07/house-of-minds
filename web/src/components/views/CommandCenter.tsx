"use client";
import { useApi } from "@/lib/api";
import { OPTION, allocation, compact, pct, signed, tone, usd, verdict } from "@/lib/format";
import type { Executive } from "@/lib/types";
import { useUI } from "@/lib/ui";

import { ErrorLine, EvidenceLink, Kpi, Loading, Panel, Pill, Scroll, verdictTone } from "../ui";

export function Overview() {
  const ui = useUI();
  const { data, error, loading, reload } = useApi<Executive>("/executive");
  if (loading && !data) return <Loading rows={6} />;
  if (error || !data) return <ErrorLine error={error} retry={reload} />;
  const x = data.data;
  const v = x.verdict;
  const pf = Object.fromEntries(x.portfolios.map((p) => [p.option, p]));
  const mgr = pf.manager_proposal_lease;
  const rec = pf[v.recommended_option];
  const diff = (rec?.expected_net_benefit_usd ?? 0) - (mgr?.expected_net_benefit_usd ?? 0);
  const weak = x.promotion.scenarios.weakest_event;
  const offered = pf.house_of_minds_with_replacements_allowed;
  const pickedReplacements = offered ? offered.allocation.split(";").filter((a) => a.includes("REPLACE")).length : null;
  const order = ["manager_proposal_lease", "house_of_minds_evidence", "house_of_minds_conditional", "no_action", "manager_proposal_buy"];

  return (
    <div className="space-y-4">
      <section className="panel p-4 sm:p-5">
        <p className="label">Replace the bottom 10? · Jan–Jun 2025 earnings</p>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className={`text-[30px] font-semibold tracking-tight ${v.answer === "REPLACE_NONE" ? "text-neg" : v.answer === "INSUFFICIENT_EVIDENCE" ? "text-warn" : "text-pos"}`}>{verdict(v.answer)}</h1>
          <p className="text-[13px] text-muted">{v.replacement_justified} of {v.machines_reviewed} replacements justified{pickedReplacements !== null && `; offered every replacement, the optimizer picked ${pickedReplacements === 0 ? "none" : pickedReplacements}`}.</p>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-4 border-t border-line pt-4 lg:grid-cols-5">
          <Kpi label="Manager plan · July net" value={signed(mgr?.expected_net_benefit_usd)} className={tone(mgr?.expected_net_benefit_usd)} sub={`${usd(mgr?.cost_usd)} to lease ${x.bottom10.filter((m) => m.verdict !== "RETIRED_ALREADY").length}`} />
          <Kpi label="Recommended · July net" value={signed(rec?.expected_net_benefit_usd)} className={tone(rec?.expected_net_benefit_usd)} sub={`${usd(rec?.cost_usd)} · ${allocation(rec?.allocation)}`} />
          <Kpi label="Difference" value={signed(diff)} className={tone(diff)} sub="same horizon and definitions" />
          <Kpi label="Budget kept" value={usd(rec?.remaining_budget_usd)} sub="of $100,000" />
          <Kpi label="Break-even uplift" value={`${usd(x.promotion.break_even)}/day`} className="text-warn" sub={`weakest event ${usd(x.promotion.a08.low)}/day → ${signed(weak)}`} title="Promotion excess theo per day needed for the recommended plan to break even" />
        </div>
        <p className="mt-3 text-[12.5px] text-warn">Main uncertainty: promotion uplift rests on 2 events with no control group.</p>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Panel title="The manager’s 10" note="Earnings rank, verdict and council agreement." flush
          right={<button type="button" onClick={() => ui.go("machines")} className="text-[12.5px] text-accent hover:underline">Investigate →</button>}>
          <Scroll>
            <table className="tbl min-w-[560px]">
              <thead><tr><th>#</th><th>Machine</th><th className="text-right">House win</th><th>Verdict</th><th className="text-right">Best-case lease</th><th className="text-right">Peer index</th><th>Council</th></tr></thead>
              <tbody>{x.bottom10.map((m) => (
                <tr key={m.machine_id} className="row-click" onClick={() => ui.go("machines", { machineId: m.machine_id })}>
                  <td className="num text-muted">{m.manager_rank}</td>
                  <td className="font-medium">{m.machine_id}</td>
                  <td className="num text-right">{usd(m.house_win_usd)}</td>
                  <td><Pill tone={verdictTone(m.verdict)}>{verdict(m.verdict)}</Pill></td>
                  <td className={`num text-right ${tone(m.lease_net_best_case_usd)}`}>{m.lease_net_best_case_usd === null ? "—" : signed(m.lease_net_best_case_usd)}</td>
                  <td className="num text-right">{m.machine_vs_peer_index.toFixed(2)}</td>
                  <td>{m.council_verdict === m.verdict ? <span className="text-[12px] text-pos">agrees</span> : <span className="text-[12px] text-neg">differs</span>}</td>
                </tr>))}</tbody>
            </table>
          </Scroll>
        </Panel>
        <div className="space-y-4">
          <Panel title="Why not">
            <ul className="space-y-2.5 text-[13px]">
              <li className="flex justify-between gap-3"><span>{v.retired_already} already retired</span><EvidenceLink id={x.bottom10.find((m) => m.verdict === "RETIRED_ALREADY")?.machine_id ?? ""} /></li>
              <li className="flex justify-between gap-3"><span>{v.inspect_instead} payout fault: inspect for {usd(x.inspection_cost_usd)}</span><EvidenceLink id={x.bottom10.find((m) => m.verdict === "DO_NOT_REPLACE_INSPECT")?.machine_id ?? ""} /></li>
              <li className="flex justify-between gap-3"><span>{v.not_economic} lose money even with the zone’s best title</span><EvidenceLink id={x.bottom10.find((m) => m.verdict === "DO_NOT_REPLACE_NOT_ECONOMIC")?.machine_id ?? ""} /></li>
              <li className="flex justify-between gap-3"><span>{v.insufficient_evidence} borderline (best case {signed(x.bottom10.find((m) => m.verdict === "INSUFFICIENT_EVIDENCE")?.lease_net_best_case_usd)})</span><EvidenceLink id={x.bottom10.find((m) => m.verdict === "INSUFFICIENT_EVIDENCE")?.machine_id ?? ""} /></li>
            </ul>
            <p className="label mt-3 border-t border-line pt-2">Floor-wide: {x.floor_planning_positive} of {x.floor_candidates} lease candidates pay back at the planning value.</p>
          </Panel>
          <Panel title="Checks">
            <dl className="grid grid-cols-2 gap-3">
              <Kpi label="Council agreement" value={`${v.council_agreement}/10`} />
              <Kpi label="Claims verified" value={`${x.council_verified}/${x.council_claims}`} />
              <Kpi label="Reconciliation" value={`${x.kpis.reconciliation_checks_passed}/14`} />
              <Kpi label="Floor hold" value={pct(x.kpis.observed_hold, 2)} sub={`${compact(x.kpis.house_win_usd)} on ${compact(x.kpis.coin_in_usd)}`} />
            </dl>
          </Panel>
        </div>
      </div>

      <Panel title="Plans compared" note={`Modeled net contribution, ${data.meta.decision_horizon}.`} flush
        right={<button type="button" onClick={() => ui.go("scenarios")} className="text-[12.5px] text-accent hover:underline">Scenarios →</button>}>
        <Scroll>
          <table className="tbl min-w-[640px]">
            <thead><tr><th>Plan</th><th>Actions</th><th className="text-right">Cost</th><th className="text-right">Net</th><th className="text-right">Tested range</th><th /></tr></thead>
            <tbody>{order.map((o) => pf[o]).filter(Boolean).map((p) => (
              <tr key={p.option}>
                <td className="font-medium">{OPTION[p.option] ?? p.option}{p.option === v.recommended_option && <span className="ml-1.5"><Pill tone="accent">recommended</Pill></span>}</td>
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
