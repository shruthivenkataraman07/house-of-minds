"use client";
import { useState } from "react";
import { CartesianGrid, Cell, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";

import { useApi } from "@/lib/api";
import { n, num, pct, signed, tone, usd, verdict } from "@/lib/format";
import { TERM, weaknessFromEarnings, weaknessFromFair } from "@/lib/terms";
import type { BankList, MachineDetail, MachinePage, Stability } from "@/lib/types";
import { useUI } from "@/lib/ui";

import { RankDumbbell, ValueBars } from "../charts";
import { F } from "@/lib/formulas";
import { How, Term } from "../explain";
import { Drawer, ErrorLine, EvidenceLink, Kpi, Loading, PageHead, Panel, Pill, Scroll, Segmented, robustTone, verdictTone } from "../ui";

const ZONES: [string, string][] = [["", "All zones"], ["Z-B40", "Back Forty"], ["Z-PIT", "Center Pit"], ["Z-ENT", "Main Entrance"],
  ["Z-HL", "High-Limit Room"], ["Z-BAR", "Bar Row"], ["Z-GAR", "Garage Entrance"], ["Z-HTL", "Hotel Corridor"]];
const SORT_LINE: Record<string, string> = {
  observed: "Lowest casino win first: rewards floor time and luck, not machine quality.",
  fair: "Weakest expected win per available hour versus comparable machines first.",
  opportunity: "Highest best-case July lease net first.",
};

export function Machines() {
  const ui = useUI();
  const [sort, setSort] = useState("observed");
  const [scope, setScope] = useState("bottom10");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const zone = ui.zoneId ?? "";
  const bank = ui.bankId ?? "";
  const limit = 50;
  const banks = useApi<BankList>("/operations/banks");
  const bankIds = (banks.data?.data.banks ?? []).filter((b) => !zone || b.zone_id === zone).map((b) => b.bank_id)
    .sort((a, b) => Number(a.slice(2)) - Number(b.slice(2)));
  const qs = new URLSearchParams({ scope, sort, offset: String(offset), limit: String(limit), ...(zone ? { zone } : {}),
    ...(bank ? { bank } : {}), ...(q.trim() ? { q: q.trim() } : {}) });
  const { data, error, loading, reload } = useApi<MachinePage>(`/machines?${qs}`);
  const page = data?.data;

  return (
    <div>
      <PageHead title="Machines" line="The lowest earners are mostly not the weakest machines once floor time and location are considered." />
      <RankingVisuals />
      <p className="label mb-2">{SORT_LINE[sort]}</p>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Segmented label="Ranking" value={sort} onChange={(s) => { setSort(s); setOffset(0); }} options={[
          { id: "observed", label: "Observed earnings" }, { id: "fair", label: "Fair performance" }, { id: "opportunity", label: "Replacement opportunity" }]} />
        <Segmented label="Scope" value={scope} onChange={(s) => { setScope(s); setOffset(0); }} options={[{ id: "bottom10", label: "Manager’s 10" }, { id: "all", label: "All 310" }]} />
        <label htmlFor="m-q" className="sr-only">Search machines</label>
        <input id="m-q" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} maxLength={40} placeholder="Machine, game or bank"
          className="w-44 rounded-md border border-line bg-surface px-2.5 py-1 text-[13px]" />
        <label htmlFor="m-zone" className="sr-only">Zone</label>
        <select id="m-zone" value={zone} onChange={(e) => { ui.set({ zoneId: e.target.value || null, bankId: null }); setOffset(0); }} className="rounded-md border border-line bg-surface px-2 py-1 text-[13px]">
          {ZONES.map(([z, l]) => <option key={z} value={z}>{l}</option>)}
        </select>
        <label htmlFor="m-bank" className="sr-only">Bank</label>
        <select id="m-bank" value={bank} onChange={(e) => { ui.set({ bankId: e.target.value || null }); setOffset(0); }} className="rounded-md border border-line bg-surface px-2 py-1 text-[13px]">
          <option value="">All banks</option>
          {bankIds.map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
      </div>
      {error && <ErrorLine error={error} retry={reload} />}
      <Panel flush>
        {loading && !page ? <div className="p-4"><Loading rows={8} /></div> : page && (
          <Scroll>
            <table className="tbl min-w-[1040px]">
              <caption className="sr-only">Machines with earnings, fair performance, availability and verdicts</caption>
              <thead><tr>
                <th>Machine</th><th className="text-right" title="Rank by total casino win; 1 = lowest">Earnings #</th><th className="text-right">Casino win</th><th className="text-right">Expected win</th>
                <th className="text-right" title="Rank vs same-game peers on expected win per available hour; 1 = weakest, 310 = strongest">Fair rank</th><th className="text-right">Availability</th><th className="text-right" title="Meter downtime for the manager's 10; scheduled minus available hours otherwise">Downtime</th><th>Location</th><th>Payout</th><th>Action</th><th>Robustness</th><th />
              </tr></thead>
              <tbody>{page.rows.map((m) => (
                <tr key={m.machine_id} className="row-click" aria-selected={ui.machineId === m.machine_id} onClick={() => ui.set({ machineId: m.machine_id })}>
                  <td><span className="font-medium">{m.machine_id}</span> <span className="label">{m.config_id}</span></td>
                  <td className="num text-right text-muted">{m.rank_raw}{m.manager_rank ? <Pill tone="muted">mgr {m.manager_rank}</Pill> : null}</td>
                  <td className="num text-right">{usd(m.house_win_usd)}</td>
                  <td className="num text-right">{usd(m.theo_usd)}<div className="label">{usd(m.theo_per_available_hour_usd, 2)}/h</div></td>
                  <td className="num text-right">{m.rank_vs_peers}</td>
                  <td className="num text-right">{pct(m.availability_rate)}</td>
                  <td className="num text-right">{m.downtime_hours === null ? "—" : `${num(m.downtime_hours, 1)} h`}</td>
                  <td className="whitespace-nowrap text-[12.5px]">{m.zone_name}<span className="label"> · {m.bank_id ?? "—"}</span></td>
                  <td>{m.payout_anomaly ? <Pill tone="accent">z {m.hit_rate_z.toFixed(0)}</Pill> : <span className="label">normal</span>}</td>
                  <td>{m.verdict ? <Pill tone={verdictTone(m.verdict)}>{verdict(m.verdict)}</Pill> : m.lease_net_best_case_usd !== null ? <span className="label">best case {signed(m.lease_net_best_case_usd)}</span> : <span className="label">keep</span>}</td>
                  <td>{m.robustness ? <Pill tone={robustTone(m.robustness)}>{m.robustness.toLowerCase()}</Pill> : <span className="label">—</span>}</td>
                  <td onClick={(e) => e.stopPropagation()}>{m.manager_rank ? <EvidenceLink id={m.machine_id} /> : null}</td>
                </tr>))}
              </tbody>
            </table>
            {page.rows.length === 0 && <p className="p-4 text-[13px] text-muted">No machines match; clear the search or zone.</p>}
          </Scroll>
        )}
        {page && page.total > limit && (
          <div className="flex items-center justify-between border-t border-line px-4 py-2 text-[12.5px]">
            <span className="label">{offset + 1}–{Math.min(offset + limit, page.total)} of {page.total}</span>
            <span className="flex gap-2">
              <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))} className="rounded border border-line px-2 py-0.5 disabled:opacity-40">Previous</button>
              <button type="button" disabled={offset + limit >= page.total} onClick={() => setOffset(offset + limit)} className="rounded border border-line px-2 py-0.5 disabled:opacity-40">Next</button>
            </span>
          </div>
        )}
      </Panel>
      {ui.machineId && !ui.evidenceId && <MachineDrawer id={ui.machineId} />}
    </div>
  );
}

function MachineDrawer({ id }: { id: string }) {
  const ui = useUI();
  const { data, error, loading, reload } = useApi<MachineDetail>(`/machines/${id}`);
  const d = data?.data;
  const m = d?.machine;
  const i = d?.investigation;
  const r = d?.robustness;
  const c = d?.candidate;
  const gaps: [string, string][] = [["Luck", "gap_luck_usd"], ["Exposure", "gap_exposure_usd"], ["Location", "gap_location_usd"], ["Configuration", "gap_game_config_usd"], ["Residual", "gap_machine_residual_usd"]];
  const max = i ? Math.max(1, ...gaps.map(([, k]) => Math.abs(n(i[k])))) : 1;
  const planning = i?.lease_net_planning_usd ?? c?.lease_net_planning_usd ?? null;
  const best = i?.lease_net_best_case_usd ?? c?.lease_net_best_case_usd ?? null;

  return (
    <Drawer label={`Machine ${id}`} onClose={() => ui.set({ machineId: null })}
      title={<><span className="label block">{d ? `${d.zone_name} · ${d.bank_id ?? "—"} · ${m?.config_id} · ${m?.manufacturer}` : "Machine"}</span>{id} {i && <Pill tone={verdictTone(String(i.verdict))}>{verdict(String(i.verdict))}</Pill>}</>}>
      {loading && <Loading rows={6} />}
      {error && <ErrorLine error={error} retry={reload} />}
      {d && m && (
        <div className="space-y-5">
          {i && <p className="text-[13px]">{String(i.recommended_alternative).replace(/^A-[A-Z-]+ \((.*)\)$/, (_m, x: string) => x.charAt(0).toUpperCase() + x.slice(1))}</p>}
          <div className="grid grid-cols-2 gap-4">
            <Kpi label="Casino win (actual)" value={usd(n(m.house_win_usd))} sub={`luck z ${n(m.luck_z).toFixed(2)}`} />
            <Kpi label="Expected casino win" value={usd(n(m.theo_usd))} sub={`coin-in ${usd(n(m.coin_in_usd))}`} />
            <Kpi label="Expected win per available hour" value={usd(n(m.theo_per_available_hour), 2)} sub={i ? `zone ${usd(n(i.zone_theo_per_available_hour), 2)} · peer index ${n(i.machine_vs_peer_index).toFixed(2)}` : `peer rank ${m.rank_vs_peers}`} />
            <Kpi label="Availability" value={pct(n(m.availability_rate))} sub={i ? `${i.active_days} active days · ${num(n(i.downtime_hours), 1)} h down` : `${num(n(m.available_hours))} available h`} />
          </div>
          {i && <p className="text-[13px] text-muted">Game pays back {pct(n(i.rtp))} of bets by design ({String(i.volatility_class)} volatility){i.retire_date ? ` · retired ${String(i.retire_date).slice(0, 10)}` : ""}.</p>}

          {d.diagnostics && <Diagnosis g={d.diagnostics} />}

          {i && (
            <section>
              <h3 className="mb-1 text-[14px] font-semibold">Why does it earn {n(d.diagnostics?.gap_vs_reference_usd ?? 0) < 0 ? "less" : "more"} than a typical machine?</h3>
              {d.diagnostics && <p className="mb-2 text-[13.5px]">A typical machine earned about {usd(n(d.diagnostics.reference_win_usd))} over six months; this one earned {usd(n(m.house_win_usd))}. These five parts add up to the {signed(n(d.diagnostics.gap_vs_reference_usd))} difference.</p>}
              <ul className="space-y-1.5">{gaps.map(([l, k]) => {
                const v = n(i[k]);
                return (
                  <li key={k} className="grid grid-cols-[110px_minmax(0,1fr)_84px] items-center gap-2 text-[13px]">
                    <span className="text-muted">{l}</span>
                    <span className="h-1.5 rounded bg-surface-2"><span className={`block h-1.5 rounded ${v < 0 ? "bg-neg/70" : "bg-pos/70"}`} style={{ width: `${(Math.abs(v) / max) * 100}%` }} /></span>
                    <span className={`num text-right ${tone(v)}`}>{signed(v)}</span>
                  </li>);
              })}</ul>
              <How steps={[
                <><b>Luck</b>: casino win minus <Term id="expected_win">expected win</Term>. Pure payout luck.</>,
                <><b>Exposure</b>: hours on the floor compared with a typical machine, valued at a typical machine’s hourly earnings.</>,
                <><b>Location</b>: how much more or less its zone earns per hour than the casino average.</>,
                <><b>Configuration</b>: how its game earns compared with other games in the same zone.</>,
                <><b>Residual</b>: what is left, which is the machine compared with identical machines nearby.</>,
                "The five parts add up exactly to the total. They show where the gap sits, not what caused it: location, game choice and the guests who play there overlap.",
              ]} technical="Sequential accounting identity against a reference machine at the floor-median rate and hours."
              formulas={d.diagnostics ? [F.decomposition(n(d.diagnostics.gap_vs_reference_usd), ["gap_luck_usd", "gap_exposure_usd", "gap_location_usd", "gap_game_config_usd", "gap_machine_residual_usd"].map((k) => n(d.diagnostics![k])))] : undefined} />
            </section>
          )}

          {(planning !== null || best !== null) && (
            <section>
              <h3 className="mb-1 text-[14px] font-semibold">Would leasing a new machine in its place pay off in July?</h3>
              <p className="mb-2 text-[13.5px]">{n(best) <= 0 ? "No. It loses money even if the new machine matched the best one ever seen in this zone." : n(planning) <= 0 ? "Only in the most optimistic case, so the evidence is not strong enough." : "Yes, at the planning value."}</p>
              <table className="tbl"><tbody>
                <tr><td>Likely case: the new machine closes half the gap to the zone’s best</td><td className={`num text-right ${tone(n(planning))}`}>{signed(n(planning))}</td></tr>
                <tr><td>Best case: it performs like the zone’s best machine</td><td className={`num text-right ${tone(n(best))}`}>{signed(n(best))}</td></tr>
                {r && <>
                  <tr><td>Cautious case: closes a quarter of the gap, a quarter taken from neighbors</td><td className={`num text-right ${tone(n(r["conservative_A10_0.25_cann_0.25"]))}`}>{signed(n(r["conservative_A10_0.25_cann_0.25"]))}</td></tr>
                  <tr><td>Best case, if the lease carried no revenue share</td><td className={`num text-right ${tone(n(r.leaseclass_adjusted_best))}`}>{signed(n(r.leaseclass_adjusted_best))}</td></tr>
                  <tr><td>Best case, if the zone’s best were 10% better still</td><td className={`num text-right ${tone(n(r["best_with_ceiling_+10pct"]))}`}>{signed(n(r["best_with_ceiling_+10pct"]))}</td></tr>
                  <tr><td>Share of the gap it must close just to break even in July</td><td className="num text-right">{pct(n(r.breakeven_A10_july), 0)}</td></tr>
                  <tr><td>Days to pay back after July, in the likely case</td><td className="num text-right">{num(n(r["payback_days_after_install_at_A10_0.5"]))} days</td></tr>
                </>}
              </tbody></table>
              {r && <p className="mt-2 flex items-center gap-2 text-[13px]"><Pill tone={robustTone(String(r.robustness))}>{String(r.robustness).toLowerCase()}</Pill><span>{r.robustness === "ROBUST" ? "Loses money in every case we tested." : r.robustness === "CONDITIONAL" ? "Loses money in the likely case; only some optimistic cases turn positive." : "Too close to call: the best case is near zero."}</span></p>}
              <How steps={[
                "A lease costs $2,500 up front plus $55 a day and takes 14 days to arrive, so it earns for 16 days of July.",
                <>The gain is the gap between this machine and the best machine in its zone, measured in <Term id="expected_win">expected win</Term> per hour, times the share of that gap a new title wins back (<Term id="gap_capture" />).</>,
                "Nobody has measured how much a new title helps, so we show the likely, best and cautious cases side by side.",
                <>Net benefit = that gain after revenue share and comps, minus the lease cost and six hours of installation downtime (<Term id="net_benefit" />).</>,
              ]} formulas={[F.leaseNet(planning === null ? undefined : n(planning), best === null ? undefined : n(best), i?.lease_cost_usd == null ? undefined : n(i.lease_cost_usd))]} />
            </section>
          )}

          {d.council_claims.length > 0 && (
            <section>
              <h3 className="mb-2 text-[12.5px] font-semibold">Council checks</h3>
              <Scroll><table className="tbl min-w-[440px]"><thead><tr><th>Check</th><th>Finding</th><th>Status</th></tr></thead>
                <tbody>{d.council_claims.map((cl) => (
                  <tr key={cl.claim_id}><td className="whitespace-nowrap text-[12.5px]">{cl.agent_name}<div className="label">{cl.kind.replace("review:", "")}</div></td>
                    <td className="text-[12.5px]">{cl.statement} <EvidenceLink id={cl.claim_id} /></td>
                    <td><Pill tone={cl.verdict === "VERIFIED" ? "pos" : "warn"}>{cl.verdict.toLowerCase()}</Pill></td></tr>))}</tbody></table></Scroll>
            </section>
          )}
          <div className="flex flex-wrap gap-3 border-t border-line pt-3">
            {i && <EvidenceLink id={id}>Machine passport</EvidenceLink>}
            {d.bank_id && <button type="button" onClick={() => ui.go("operations", { tab: "banks", bankId: d.bank_id, machineId: id })} className="text-[12px] text-accent hover:underline">Bank {d.bank_id} history ↗</button>}
          </div>
        </div>
      )}
    </Drawer>
  );
}

const VCOL: Record<string, string> = { RETIRED_ALREADY: "var(--chart-2)", DO_NOT_REPLACE_INSPECT: "var(--accent)",
  DO_NOT_REPLACE_NOT_ECONOMIC: "var(--neg)", INSUFFICIENT_EVIDENCE: "var(--warn)", REPLACE_JUSTIFIED_CONDITIONAL: "var(--pos)" };

function RankingVisuals() {
  const ui = useUI();
  const ten = useApi<MachinePage>("/machines?scope=bottom10&limit=10");
  const all = useApi<MachinePage>("/machines?scope=all&limit=310");
  const rows = ten.data?.data.rows ?? [];
  const pts = (all.data?.data.rows ?? []).map((m) => ({ ...m, x: m.available_hours, y: m.theo_per_available_hour_usd, z: m.theo_usd }));
  return (
    <div className="mb-4 grid gap-4 xl:grid-cols-2">
      <Panel title="Where do the manager’s 10 really rank?" note="Red: rank by casino win · blue: rank vs comparable machines (1 = weakest of 310).">
        {ten.error ? <ErrorLine error={ten.error} retry={ten.reload} /> : !rows.length ? <Loading rows={4} /> : (
          <RankDumbbell label="Earnings rank versus fair rank" max={310} aLabel={TERM.earnings_rank} bLabel={TERM.fair_rank} selected={ui.machineId}
            rows={rows.map((m) => ({ key: m.machine_id, label: m.machine_id, a: weaknessFromEarnings(m.rank_raw), b: weaknessFromFair(m.rank_vs_peers), onClick: () => ui.set({ machineId: m.machine_id }) }))} />)}
        <p className="mt-2 text-[13.5px]">Red is where the manager’s ranking puts each machine (by total casino win). Blue is where it really stands against identical machines. A long line means its low total came from floor time, location or luck, not from the machine.</p>
      </Panel>
      <Panel title="Does low exposure explain low earnings?" note={`All 310 machines · x: available hours · y: ${TERM.theo_per_hour.toLowerCase()} · size: expected win`}>
        {all.error ? <ErrorLine error={all.error} retry={all.reload} /> : !pts.length ? <Loading rows={4} /> : (
          <div className="h-64" role="img" aria-label="Scatterplot of available hours versus expected win per available hour for 310 machines">
            <ResponsiveContainer><ScatterChart margin={{ left: 0, right: 8, top: 6, bottom: 4 }}>
              <CartesianGrid stroke="var(--line)" />
              <XAxis type="number" dataKey="x" name="Available hours" stroke="var(--muted)" fontSize={11} tickLine={false} tickFormatter={(v: number) => num(v)} />
              <YAxis type="number" dataKey="y" name="Expected win / hour" stroke="var(--muted)" fontSize={11} tickLine={false} width={44} tickFormatter={(v: number) => `$${v}`} />
              <ZAxis type="number" dataKey="z" range={[14, 90]} name="Expected win" />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 12 }}
                formatter={(v, k) => [k === "Available hours" ? num(Number(v)) : k === "Expected win / hour" ? usd(Number(v), 2) : usd(Number(v)), String(k)]} />
              <Scatter isAnimationActive={false} data={pts} onClick={(p) => { const id = (p as unknown as { machine_id?: string }).machine_id; if (id) ui.set({ machineId: id }); }}>
                {pts.map((m) => <Cell key={m.machine_id} cursor="pointer" fill={m.verdict ? VCOL[m.verdict] ?? "var(--accent)" : "var(--chart-2)"} fillOpacity={m.verdict ? 0.95 : 0.35} stroke={ui.machineId === m.machine_id ? "var(--text)" : "none"} strokeWidth={2} />)}
              </Scatter>
            </ScatterChart></ResponsiveContainer>
          </div>)}
        <p className="mt-2 text-[13.5px]">Each dot is a machine. Most sat on the floor the whole six months (the band on the right). Colored dots are the manager’s 10; they sit low on earnings per hour, but so do many machines nobody proposed replacing.</p>
      </Panel>
      <StabilityPanel />
    </div>
  );
}

/** Payout Monte Carlo of the raw earnings ranking (API: /machines/stability). */
function StabilityPanel() {
  const ui = useUI();
  const { data, error, reload } = useApi<Stability>("/machines/stability");
  if (error) return <div className="xl:col-span-2"><ErrorLine error={error} retry={reload} /></div>;
  if (!data) return <div className="xl:col-span-2"><Loading rows={3} /></div>;
  const s = data.data.summary;
  return (
    <Panel className="xl:col-span-2" title="Would the same 10 machines be lowest again?"
      note={`${num(n(s.simulations))} payout simulations (seed ${String(s.seed)}): only payout luck varies; floor time, bets and game math stay fixed.`}>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="min-w-0 max-w-[760px]"><ValueBars label="Probability of falling in the lowest 10 by casino win" format={(v) => `${v.toFixed(0)}%`} selected={ui.machineId}
          rows={data.data.rows.filter((r, i) => n(r.rank_raw) <= 10 || i < 14).map((r) => ({ key: String(r.machine_id), label: `${String(r.machine_id)}${n(r.rank_raw) <= 10 ? ` · manager #${String(r.rank_raw)}` : ""}`,
            value: Math.round(n(r.p_raw_bottom10_sim) * 1000) / 10, tone: n(r.rank_raw) <= 10 ? (n(r.p_raw_bottom10_sim) < 0.5 ? "warn" : "accent") : "muted",
            note: `rank ${n(r.raw_rank_p05_sim).toFixed(0)}–${n(r.raw_rank_p95_sim).toFixed(0)}`, onClick: () => ui.set({ machineId: String(r.machine_id) }) }))} /></div>
        <dl className="space-y-3 text-[12.5px]">
          <div><dt className="label">Manager’s 10 still lowest (average)</dt><dd className="num text-[18px] font-semibold">{n(s.manager_list_mean_overlap).toFixed(1)} of 10</dd></div>
          <div><dt className="label">All 10 lowest together</dt><dd className="num text-[18px] font-semibold">{pct(n(s.manager_list_all10_share), 1)}</dd><dd className="label">of simulations</dd></div>
          <div><dt className="label">Fair ranking</dt><dd>{String(s.fair_ranking_note)}.</dd></div>
          <div><dt className="label">Assumption</dt><dd className="text-muted">{String(s.assumption)}.</dd></div>
        </dl>
      </div>
      <p className="mt-2 text-[13.5px]">Each bar is how often a machine landed in the lowest 10 when we replayed the six months 2,000 times with fresh random payouts. Amber marks a manager-list machine that stays there less than half the time: luck put it on the list. “Rank” is the range of places it landed in.</p>
    </Panel>
  );
}

/** Statistical diagnosis for one machine; every value comes from the diagnostics export. */
function Diagnosis({ g }: { g: Record<string, string | number | boolean | null> }) {
  const z = n(g.luck_z), hitP = n(g.hit_p_exact_bonferroni), pB = n(g.p_raw_bottom10_sim);
  const flags: { t: string; tone: "warn" | "accent" | "muted" | "pos" }[] = [];
  if (hitP < 0.001) flags.push({ t: "Possible payout anomaly (statistical, not proven fault)", tone: "accent" });
  if (z <= -1.96 && hitP >= 0.001) flags.push({ t: "Unfavorable payout luck", tone: "warn" });
  if (z <= -1.96 && hitP < 0.001) flags.push({ t: "Shortfall consistent with the payout anomaly, not luck", tone: "warn" });
  if (z >= 1.96) flags.push({ t: "Favorable payout luck", tone: "muted" });
  if (n(g.loo_peer_index) < 0.95) flags.push({ t: "Below comparable machines", tone: "warn" });
  if (n(g.loo_peer_index) >= 1.05) flags.push({ t: "Above comparable machines", tone: "pos" });
  if (!flags.length) flags.push({ t: "No distinct statistical signal", tone: "muted" });
  return (
    <section>
      <h3 className="mb-1 text-[14px] font-semibold">Bad luck, a payout fault, or a weak machine?</h3>
      <div className="mb-3 flex flex-wrap gap-1.5">{flags.map((f) => <Pill key={f.t} tone={f.tone}>{f.t}</Pill>)}</div>
      <dl className="space-y-3 text-[13.5px] leading-relaxed">
        <div>
          <dt className="font-medium">Was it unlucky?</dt>
          <dd>It won {usd(Math.abs(n(g.luck_residual_usd)))} {n(g.luck_residual_usd) < 0 ? "less" : "more"} than its games should have. A normal swing for this machine is about {usd(n(g.luck_residual_sd_usd))}, so that is {Math.abs(z).toFixed(1)} normal swings ({Math.abs(z) < 2 ? "within ordinary luck" : Math.abs(z) < 3 ? "unusual but possible" : "far beyond ordinary luck"}).</dd>
        </div>
        <div>
          <dt className="font-medium">Does it pay out as often as its game should?</dt>
          <dd>It paid out on {pct(n(g.observed_hit_rate), 1)} of {num(n(g.paid_spins))} spins; the game is designed for {pct(n(g.expected_hit_probability), 1)}. {hitP < 0.001 ? "A gap that large, over that many spins, is almost impossible by chance (even allowing for checking 310 machines). Inspect the meters and paytable." : "That is within what chance allows."}</dd>
        </div>
        <div>
          <dt className="font-medium">Is it weaker than identical machines nearby?</dt>
          <dd>It earns {n(g.loo_peer_index).toFixed(2)}× what {String(g.loo_peer_n)} comparable machines earn per hour ({String(g.loo_peer_basis)}, not counting itself){n(g.loo_peer_index) < 0.95 ? ", a little weaker." : n(g.loo_peer_index) >= 1.05 ? ", so the machine itself is not the problem." : ", about the same."}</dd>
        </div>
        <div>
          <dt className="font-medium">Would it be in the lowest 10 again?</dt>
          <dd>In {pct(pB, 0)} of 2,000 replays with fresh random payouts (its rank ranged from {n(g.raw_rank_p05_sim).toFixed(0)} to {n(g.raw_rank_p95_sim).toFixed(0)}). {pB < 0.5 ? "Its place on the manager’s list owes a lot to luck." : "Its low ranking is consistent."}</dd>
        </div>
      </dl>
      <How steps={[
        <>Luck: we compare actual <Term id="casino_win">casino win</Term> with <Term id="expected_win">expected win</Term>, and measure the gap in normal swings for this machine’s bets and game (<Term id="luck_z" />).</>,
        <>Paying spins: we count spins that paid anything and compare with the game’s design rate (<Term id="paying_spins" />), then raise the bar because we test 310 machines (<Term id="multiple_testing" />).</>,
        <>Comparable machines: same game, same zone, excluding this machine so it cannot pull its own benchmark (<Term id="comparable" />).</>,
        <>Replays: 2,000 simulated six-month runs where only payout luck changes (<Term id="simulation" />).</>,
        "A statistical anomaly is a strong signal, not proof of a fault; an inspection confirms it.",
      ]} technical={`Luck sd = √(Σ bet² × payout-multiplier variance), independent spins. Exact binomial test, Bonferroni ×310 (p ${hitP < 0.001 ? "< 0.001" : hitP.toFixed(3)}). Luck p (Bonferroni) ${n(g.luck_p_bonferroni) < 0.001 ? "< 0.001" : n(g.luck_p_bonferroni).toFixed(3)}. Monte Carlo seed 20250701, normal approximation. Gap parts sum to the total within ${usd(Math.abs(n(g.decomposition_error_usd)), 2)}.`}
        formulas={[F.luckZ(n(g.house_win_usd), n(g.theo_usd), n(g.luck_residual_sd_usd), z), F.payingSpins(n(g.paying_spins), n(g.paid_spins), n(g.expected_hit_probability), hitP),
          F.peerIndex(n(g.loo_peer_index), n(g.loo_peer_n)), F.simulation(pB)]} />
    </section>
  );
}
