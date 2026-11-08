"use client";
import type { ReactNode } from "react";
import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useApi } from "@/lib/api";
import { allocation, compact, n, pct, pp, signed, tone, typo, usd, verdict } from "@/lib/format";
import type { Comps, Demand, Downtime, EvidenceList, Executive, Players, Portfolios, Stability } from "@/lib/types";
import { type ViewId, useUI } from "@/lib/ui";

import { type ChartTone, CompositionBar } from "../charts";
import { ErrorLine, EvidenceLink, Loading, PageHead, Pill, VERDICT_TONE } from "../ui";

const VTONE = VERDICT_TONE as Record<string, ChartTone>;
const TT = { contentStyle: { background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 11 } };

/** Final summary: every figure comes from the same endpoints its source tab uses. */
export function Answers() {
  const ex = useApi<Executive>("/executive");
  const dm = useApi<Demand>("/operations/demand");
  const dt = useApi<Downtime>("/operations/downtime");
  const pl = useApi<Players>("/players/summary");
  const cp = useApi<Comps>("/loyalty/comps");
  const pf = useApi<Portfolios>("/portfolios");
  const ev = useApi<EvidenceList>("/evidence?limit=200");
  const st = useApi<Stability>("/machines/stability");
  const all = [ex, dm, dt, pl, cp, pf, ev, st];
  const err = all.find((x) => x.error)?.error;
  if (err) return <ErrorLine error={err} retry={() => all.forEach((x) => x.reload())} />;
  if (!ex.data || !dm.data || !dt.data || !pl.data || !cp.data || !pf.data || !ev.data || !st.data) return <Loading rows={8} />;
  const stab = st.data.data.summary;

  const x = ex.data.data, v = x.verdict;
  const claimFor = (cat: string) => ev.data!.data.claims.find((c) => c.category === cat)?.claim_id as string | undefined;
  const b10 = x.bottom10;
  const betterHalf = b10.filter((m) => m.rank_vs_peers > 155).length; // rank 1 = weakest of 310
  const shortFloor = b10.filter((m) => m.active_days < 150).length;
  const fault = b10.find((m) => m.verdict === "DO_NOT_REPLACE_INSPECT");
  const insuff = b10.find((m) => m.verdict === "INSUFFICIENT_EVIDENCE");
  const counts = b10.reduce<Record<string, number>>((a, m) => ({ ...a, [m.verdict]: (a[m.verdict] ?? 0) + 1 }), {});
  const d = dm.data.data, [e1, e2] = d.explanations;
  const t = dt.data.data.totals;
  const peak = [...dt.data.data.by_hour].sort((a, b) => n(b.downtime_hours) - n(a.downtime_hours))[0];
  const topMfr = dt.data.data.by_manufacturer[0];
  const p = pl.data.data.summary;
  const months = cp.data.data.months, c0 = months[0], cN = months[months.length - 1];
  const compCost = months.reduce((s, r) => s + n(r.comp_cost_usd), 0);
  const ports = Object.fromEntries(pf.data.data.options.map((o) => [o.option, o]));
  const rec = ports[v.recommended_option], mgr = ports.manager_proposal_lease;
  const promo = pf.data.data.promotion;
  const weak = promo.scenarios.find((s) => s.scenario === "weakest_event");
  const zero = promo.scenarios.find((s) => s.scenario === "zero_uplift");
  const noPromo = promo.reoptimised_promo_prohibited.conditional;
  const diff = n(rec?.expected_net_benefit_usd) - n(mgr?.expected_net_benefit_usd);
  const recPassport = pf.data.data.passports.find((q) => q.portfolio_mode === "evidence_supported");
  const plan = pf.data.data.measurement_plans.find((m) => m.action_id === "A-PROMO");

  return (
    <div className="space-y-4">
      <PageHead title="Answers" line={`Replace none of the ten. ${allocation(rec?.allocation)} for ${usd(rec?.cost_usd)} beats the manager’s plan by ${signed(diff)}.`} />
      <ol className="grid gap-3 lg:grid-cols-2">
        <Answer n={1} q="Which machines are genuinely weak?" go="machines" evidence={b10[0]?.machine_id}
          lines={[
            <>None of the manager’s 10 should be replaced: {v.replacement_justified} of {v.machines_reviewed} replacements are justified.</>,
            <>{v.retired_already} already left the floor, {v.inspect_instead} has a payout fault{fault ? ` (${fault.machine_id})` : ""}, and {v.not_economic} lose money on a July lease even with the zone’s best title.</>,
            <>Low totals mostly reflect floor time and location: {betterHalf} of 10 rank in the better half of comparable machines; {shortFloor} had under 150 days on the floor.</>,
            <>The list itself is partly luck: in {Number(stab.simulations).toLocaleString("en-US")} payout simulations only {n(stab.manager_list_mean_overlap).toFixed(1)} of the 10 stay lowest on average. {insuff ? `${insuff.machine_id} is borderline (best-case lease ${signed(insuff.lease_net_best_case_usd)}).` : ""}</>,
          ]}
          chart={<CompositionBar label="Manager's 10 by verdict" segments={Object.entries(counts).map(([k, c]) => ({ key: k, label: verdict(k), value: c, tone: VTONE[k] ?? "muted" }))} />} />

        <Answer n={2} q="What changed in demand?" go="operations" tab="demand" evidence={claimFor("zone_demand")}
          lines={[
            <>{String(e1?.change)}: {pp(n(e1?.observed_pct))}.</>,
            <>Per available machine-hour it fell {Math.abs(n(e1?.result_pct)).toFixed(1)}%, so fewer machines do not explain the drop.</>,
            <>{e2 ? `${String(e2.change)}: ${pp(n(e2.observed_pct))}; ${typo(e2.conclusion)}.` : ""}</>,
            <>Back Forty’s weak earnings are a location and traffic problem before they are a machine problem.</>,
          ]}
          chart={<Mini h={64} label="Weekly amount wagered per day"><LineChart data={d.weekly}><XAxis dataKey="week_start" hide /><YAxis hide domain={["auto", "auto"]} />
            <Tooltip {...TT} formatter={(val) => [usd(Number(val)), "Wagered per day"]} labelFormatter={(l) => `Week of ${String(l)}`} />
            <Line isAnimationActive={false} dataKey="coin_in_per_day_usd" stroke="var(--accent)" dot={false} strokeWidth={1.75} /></LineChart></Mini>} />

        <Answer n={3} q="How much play was lost to downtime?" go="operations" tab="downtime" evidence={claimFor("downtime")}
          lines={[
            <>Machines were down {n(t.downtime_hours).toLocaleString("en-US", { maximumFractionDigits: 0 })} machine-hours ({pct(1 - n(t.availability), 2)} of scheduled time).</>,
            <>That put {usd(t.theo_at_risk_usd)} of expected casino win at risk ({usd(t.contribution_at_risk_usd)} after revenue share and comps).</>,
            <>This is a modeled opportunity, not an observed loss: some play moves to nearby machines.</>,
            <>Focus maintenance on {String(topMfr?.manufacturer)} and coverage around {peak ? `${String(peak.local_hour).padStart(2, "0")}:00` : "peak hours"}, the worst hour.</>,
          ]}
          chart={<Mini h={64} label="Downtime hours by local hour"><BarChart data={dt.data.data.by_hour}><XAxis dataKey="local_hour" hide /><YAxis hide />
            <Tooltip {...TT} formatter={(val) => [`${Math.round(Number(val))} h`, "Downtime"]} labelFormatter={(l) => `${String(l).padStart(2, "0")}:00`} />
            <Bar isAnimationActive={false} dataKey="downtime_hours" fill="var(--accent)" /></BarChart></Mini>} />

        <Answer n={4} q="What happened to tracked players?" go="operations" tab="players" evidence={claimFor("guest_behavior")}
          lines={[
            <>Tracked players wagered {compact(n(p.tracked_coin_in_usd))} and lost {compact(-n(p.tracked_player_net_usd))} net; {pct(n(p.share_players_ahead))} finished ahead.</>,
            <>Play is concentrated: the top 10% of players generate {pct(n(p.top10pct_share_of_theo))} of tracked expected win (Gini {n(p.gini_theo).toFixed(2)}).</>,
            <>Carded play is {pct(n(p.carded_share_of_all_coin_in))} of all wagers, so these figures never mix with whole-floor totals.</>,
            <>Use tier-level economics for program design; individual players are not shown or targeted.</>,
          ]}
          chart={<CompositionBar label="Share of tracked expected win" segments={[
            { key: "t1", label: "Top 1% of players", value: Math.round(n(p.top1pct_share_of_theo) * 1000) / 10, display: pct(n(p.top1pct_share_of_theo)), tone: "accent" },
            { key: "t9", label: "Next 9%", value: Math.round((n(p.top10pct_share_of_theo) - n(p.top1pct_share_of_theo)) * 1000) / 10, display: pct(n(p.top10pct_share_of_theo) - n(p.top1pct_share_of_theo)), tone: "warn" },
            { key: "r", label: "Other 90%", value: Math.round((1 - n(p.top10pct_share_of_theo)) * 1000) / 10, display: pct(1 - n(p.top10pct_share_of_theo)), tone: "muted" }]} />} />

        <Answer n={5} q="What happened to the comp program?" go="operations" tab="comps" evidence={claimFor("comp_economics")}
          lines={[
            <>Points needed per comp dollar fell from {n(c0?.points_per_comp_usd).toFixed(1)} to {n(cN?.points_per_comp_usd).toFixed(1)} after May 1, 2025.</>,
            <>Loyalty reward cost was {usd(compCost)} over Jan–Jun; cost per tracked expected win rose from {pct(n(c0?.comp_cost_per_carded_theo), 2)} to {pct(n(cN?.comp_cost_per_carded_theo), 2)}.</>,
            <>The program became more generous while demand softened, so margin per tracked dollar fell.</>,
            <>Whether the change bought extra play is not identified (no control group); test it with a holdout pilot.</>,
          ]}
          chart={<Mini h={64} label="Points per comp dollar by month"><BarChart data={months.map((m) => ({ month: String(m.month), v: n(m.points_per_comp_usd) }))}><XAxis dataKey="month" hide /><YAxis hide />
            <Tooltip {...TT} formatter={(val) => [Number(val).toFixed(1), "Points per $"]} />
            <Bar isAnimationActive={false} dataKey="v" fill="var(--accent)" /></BarChart></Mini>} />

        <Answer n={6} q="What should management do with $100K?" go="investment" evidence={recPassport?.passport_id as string | undefined}
          lines={[
            <>Fund {allocation(rec?.allocation)} for {usd(rec?.cost_usd)} and keep {usd(rec?.remaining_budget_usd)} unspent.</>,
            <>Modeled July net is {signed(rec?.expected_net_benefit_usd)}, versus {signed(mgr?.expected_net_benefit_usd)} for the manager’s lease plan ({signed(diff)}).</>,
            <>Uncertain: break-even is {usd(promo.break_even_A08)}/day of extra expected win; the weaker past event gives {signed(weak?.original_evidence)} and zero uplift {signed(zero?.original_evidence)}. Without promotions the best plan nets {signed(noPromo?.net)}.</>,
            <>Measure: {plan ? String(plan.success_threshold) : "see measurement plan"}.</>,
          ]}
          chart={<CompositionBar label="Budget use" segments={[
            { key: "spend", label: "Spend", value: n(rec?.cost_usd), display: usd(rec?.cost_usd), tone: "accent" },
            { key: "keep", label: "Keep unused", value: n(rec?.remaining_budget_usd), display: usd(rec?.remaining_budget_usd), tone: "muted" }]} />} />
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

function Mini({ h, label, children }: { h: number; label: string; children: React.ReactElement }) {
  return <div style={{ height: h }} role="img" aria-label={label}><ResponsiveContainer>{children}</ResponsiveContainer></div>;
}

function Answer({ n: num, q, lines, chart, go, tab, evidence }: { n: number; q: string; lines: ReactNode[]; chart: ReactNode; go: ViewId; tab?: string; evidence?: string }) {
  const ui = useUI();
  return (
    <li className="panel flex flex-col p-4">
      <p className="label">Question {num}</p>
      <h2 className="text-[14.5px] font-semibold">{q}</h2>
      <p className="mt-1.5 text-[13.5px] font-medium">{lines[0]}</p>
      <ul className="mt-1 space-y-1 text-[13px] text-ink/85">{lines.slice(1).map((l, i) => <li key={i}>{l}</li>)}</ul>
      <div className="mt-3 border-t border-line pt-3">{chart}</div>
      <div className="mt-auto flex flex-wrap items-center gap-3 pt-3">
        <button type="button" onClick={() => ui.go(go, tab ? { tab } : undefined)} className="text-[12px] text-accent hover:underline">Explore {go}{tab ? ` · ${tab}` : ""} →</button>
        {evidence ? <EvidenceLink id={evidence} /> : <Pill tone="warn">no evidence record</Pill>}
      </div>
    </li>
  );
}

function Fact({ label, value, sub, cls = "" }: { label: string; value: string; sub?: string; cls?: string }) {
  return <div className="min-w-0"><p className="label">{label}</p><p className={`num mt-0.5 text-[18px] font-semibold ${cls}`}>{value}</p>{sub && <p className="label">{sub}</p>}</div>;
}
