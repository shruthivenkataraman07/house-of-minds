"use client";
import type { ReactNode } from "react";

import { useApi } from "@/lib/api";
import { allocation, compact, n, pct, signed, tone, usd, verdict } from "@/lib/format";
import type { Comps, Demand, Downtime, EvidenceList, Executive, Players, Portfolios } from "@/lib/types";
import { type ViewId, useUI } from "@/lib/ui";

import { ErrorLine, EvidenceLink, Loading, PageHead, Pill } from "../ui";

/** Final summary: every figure comes from the same endpoints its source tab uses. */
export function Answers() {
  const ex = useApi<Executive>("/executive");
  const dm = useApi<Demand>("/operations/demand");
  const dt = useApi<Downtime>("/operations/downtime");
  const pl = useApi<Players>("/players/summary");
  const cp = useApi<Comps>("/loyalty/comps");
  const pf = useApi<Portfolios>("/portfolios");
  const ev = useApi<EvidenceList>("/evidence?limit=200");
  const all = [ex, dm, dt, pl, cp, pf, ev];
  const err = all.find((x) => x.error)?.error;
  if (err) return <ErrorLine error={err} retry={() => all.forEach((x) => x.reload())} />;
  if (!ex.data || !dm.data || !dt.data || !pl.data || !cp.data || !pf.data || !ev.data) return <Loading rows={8} />;

  const x = ex.data.data, v = x.verdict;
  const claimFor = (cat: string) => ev.data!.data.claims.find((c) => c.category === cat)?.claim_id as string | undefined;
  const b10 = x.bottom10;
  const peerTop = b10.filter((m) => m.rank_vs_peers <= 155).length;
  const d = dm.data.data, [e1, e2] = d.explanations;
  const t = dt.data.data.totals;
  const p = pl.data.data.summary;
  const months = cp.data.data.months, c0 = months[0], cN = months[months.length - 1];
  const compCost = months.reduce((s, r) => s + n(r.comp_cost_usd), 0);
  const ports = Object.fromEntries(pf.data.data.options.map((o) => [o.option, o]));
  const rec = ports[v.recommended_option], mgr = ports.manager_proposal_lease;
  const promo = pf.data.data.promotion;
  const weak = promo.scenarios.find((s) => s.scenario === "weakest_event");
  const diff = n(rec?.expected_net_benefit_usd) - n(mgr?.expected_net_benefit_usd);
  const bestInsuff = b10.find((m) => m.verdict === "INSUFFICIENT_EVIDENCE");

  return (
    <div className="space-y-4">
      <PageHead title="Answers" line="Six questions. Six evidence-backed conclusions." />
      <ol className="grid gap-3 lg:grid-cols-2">
        <Answer n={1} q="Which machines truly underperform?" go="machines" evidence={b10[0]?.machine_id}
          a={<>{verdict(v.answer)}: {v.replacement_justified} of {v.machines_reviewed} replacements justified.</>}
          facts={[["Manager’s 10", `${v.retired_already} retired · ${v.inspect_instead} inspect · ${v.not_economic} not economic · ${v.insufficient_evidence} insufficient`],
            ["Fair ranking", `${peerTop} of 10 sit in the better half of same-game peers (rank ≤ 155 of 310)`],
            ["Borderline", bestInsuff ? `${bestInsuff.machine_id}: best-case lease ${signed(bestInsuff.lease_net_best_case_usd)}, ${bestInsuff.active_days} days on floor` : "none"]]} />
        <Answer n={2} q="What changed in demand?" go="operations" tab="demand" evidence={claimFor("zone_demand")}
          a={<>{String(e1?.change)}: {n(e1?.observed_pct).toFixed(1)}%; per available hour {n(e1?.result_pct).toFixed(1)}%.</>}
          facts={[["Floor coin-in", `${compact(d.totals.coin_in_usd)} over ${d.totals.days} days`],
            ["Zone", e2 ? `${String(e2.change)}: ${n(e2.observed_pct).toFixed(1)}%` : "—"],
            ["Explanation", String(e1?.conclusion ?? "—")]]} />
        <Answer n={3} q="How much was lost to downtime?" go="operations" tab="downtime" evidence={claimFor("downtime")}
          a={<>{n(t.downtime_hours).toLocaleString("en-US", { maximumFractionDigits: 0 })} machine-hours down; {usd(t.theo_at_risk_usd)} theoretical win at risk.</>}
          facts={[["Availability", pct(t.availability, 2)], ["Contribution at risk", usd(t.contribution_at_risk_usd)],
            ["Basis", "Modeled opportunity, not observed loss"]]} />
        <Answer n={4} q="What happened to tracked players?" go="operations" tab="players" evidence={claimFor("guest_behavior")}
          a={<>Tracked players lost {compact(-n(p.tracked_player_net_usd))} net; {pct(n(p.share_players_ahead))} finished ahead.</>}
          facts={[["Tracked wagers", compact(n(p.tracked_coin_in_usd))], ["Concentration", `Top 10% = ${pct(n(p.top10pct_share_of_theo))} of tracked theo`],
            ["Population", `Carded play only (${pct(n(p.carded_share_of_all_coin_in))} of coin-in)`]]} />
        <Answer n={5} q="What happened to comps?" go="operations" tab="comps" evidence={claimFor("comp_economics")}
          a={<>Points per comp dollar fell from {n(c0?.points_per_comp_usd).toFixed(1)} to {n(cN?.points_per_comp_usd).toFixed(1)}; cost per carded theo rose.</>}
          facts={[["Comp cost", `${usd(compCost)} (${String(c0?.month)}–${String(cN?.month)})`],
            ["Cost per carded theo", `${pct(n(c0?.comp_cost_per_carded_theo), 2)} → ${pct(n(cN?.comp_cost_per_carded_theo), 2)}`],
            ["Causality", "Incremental play from the change is not identified"]]} />
        <Answer n={6} q="What should the casino fund?" go="investment" evidence={pf.data.data.passports.find((x) => x.portfolio_mode === "evidence_supported")?.passport_id as string | undefined}
          a={<>Fund {allocation(rec?.allocation)} for {usd(rec?.cost_usd)}; keep {usd(rec?.remaining_budget_usd)}.</>}
          facts={[["Modeled July net", signed(rec?.expected_net_benefit_usd)], ["Remaining budget", usd(rec?.remaining_budget_usd)],
            ["Uncertainty", `Break-even ${usd(promo.break_even_A08)}/day; weakest event gives ${signed(weak?.original_evidence)}`]]} />
      </ol>

      <section className="panel p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-[13px] font-semibold">Manager’s proposal vs House of Minds</h2>
          <EvidenceLink id={v.recommended_option}>Plan evidence</EvidenceLink>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Fact label="Manager · lease" value={signed(mgr?.expected_net_benefit_usd)} cls={tone(mgr?.expected_net_benefit_usd)} sub={`${usd(mgr?.cost_usd)} spent`} />
          <Fact label="House of Minds" value={signed(rec?.expected_net_benefit_usd)} cls={tone(rec?.expected_net_benefit_usd)} sub={`${usd(rec?.cost_usd)} spent`} />
          <Fact label="Modeled difference" value={signed(diff)} cls={tone(diff)} sub={ex.data.meta.decision_horizon} />
          <Fact label="Unresolved risk" value="Promotion uplift" cls="text-warn" sub="2 events, no control group" />
        </div>
      </section>
    </div>
  );
}

function Answer({ n: num, q, a, facts, go, tab, evidence }: { n: number; q: string; a: ReactNode; facts: [string, string][]; go: ViewId; tab?: string; evidence?: string }) {
  const ui = useUI();
  return (
    <li className="panel flex flex-col p-4">
      <p className="label">Question {num}</p>
      <h2 className="text-[14px] font-semibold">{q}</h2>
      <p className="mt-1.5 text-[13.5px]">{a}</p>
      <dl className="mt-3 space-y-1 border-t border-line pt-2.5">
        {facts.map(([k, val]) => (
          <div key={k} className="grid grid-cols-[132px_minmax(0,1fr)] gap-2 text-[12.5px]"><dt className="text-muted">{k}</dt><dd className="num truncate" title={val}>{val}</dd></div>))}
      </dl>
      <div className="mt-auto flex flex-wrap items-center gap-3 pt-3">
        <button type="button" onClick={() => ui.go(go, tab ? { tab } : undefined)} className="text-[12px] text-accent hover:underline">Open {go}{tab ? ` · ${tab}` : ""} →</button>
        {evidence ? <EvidenceLink id={evidence} /> : <Pill tone="warn">no evidence record</Pill>}
      </div>
    </li>
  );
}

function Fact({ label, value, sub, cls = "" }: { label: string; value: string; sub?: string; cls?: string }) {
  return <div className="min-w-0"><p className="label">{label}</p><p className={`num mt-0.5 text-[18px] font-semibold ${cls}`}>{value}</p>{sub && <p className="label">{sub}</p>}</div>;
}
