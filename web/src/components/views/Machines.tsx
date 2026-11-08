"use client";
import { useState } from "react";
import { CartesianGrid, Cell, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";

import { useApi } from "@/lib/api";
import { n, num, pct, signed, tone, usd, verdict } from "@/lib/format";
import { TERM, weaknessFromEarnings, weaknessFromFair } from "@/lib/terms";
import type { BankList, MachineDetail, MachinePage } from "@/lib/types";
import { useUI } from "@/lib/ui";

import { RankDumbbell } from "../charts";
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
          {i && <p className="text-[13px]">{String(i.recommended_alternative)}</p>}
          <div className="grid grid-cols-2 gap-4">
            <Kpi label="Casino win (actual)" value={usd(n(m.house_win_usd))} sub={`luck z ${n(m.luck_z).toFixed(2)}`} />
            <Kpi label="Expected casino win" value={usd(n(m.theo_usd))} sub={`coin-in ${usd(n(m.coin_in_usd))}`} />
            <Kpi label="Expected win per available hour" value={usd(n(m.theo_per_available_hour), 2)} sub={i ? `zone ${usd(n(i.zone_theo_per_available_hour), 2)} · peer index ${n(i.machine_vs_peer_index).toFixed(2)}` : `peer rank ${m.rank_vs_peers}`} />
            <Kpi label="Availability" value={pct(n(m.availability_rate))} sub={i ? `${i.active_days} active days · ${num(n(i.downtime_hours), 1)} h down` : `${num(n(m.available_hours))} available h`} />
          </div>
          {i && <p className="label">RTP {pct(n(i.rtp))} · {String(i.volatility_class)} volatility · hit-rate z {n(i.hit_rate_z).toFixed(2)} (Bonferroni p {n(i.hit_p_bonferroni) < 0.001 ? "< 0.001" : n(i.hit_p_bonferroni).toFixed(2)}){i.retire_date ? ` · retired ${String(i.retire_date).slice(0, 10)}` : ""}</p>}

          {i && (
            <section>
              <h3 className="mb-2 text-[12.5px] font-semibold">Earnings gap attribution</h3>
              <ul className="space-y-1.5">{gaps.map(([l, k]) => {
                const v = n(i[k]);
                return (
                  <li key={k} className="grid grid-cols-[96px_minmax(0,1fr)_76px] items-center gap-2 text-[12.5px]">
                    <span className="text-muted">{l}</span>
                    <span className="h-1.5 rounded bg-surface-2"><span className={`block h-1.5 rounded ${v < 0 ? "bg-neg/70" : "bg-pos/70"}`} style={{ width: `${(Math.abs(v) / max) * 100}%` }} /></span>
                    <span className={`num text-right ${tone(v)}`}>{signed(v)}</span>
                  </li>);
              })}</ul>
              <p className="label mt-1">Attribution, not causation: location, configuration and player mix are confounded.</p>
            </section>
          )}

          {(planning !== null || best !== null) && (
            <section>
              <h3 className="mb-2 text-[12.5px] font-semibold">July lease replacement (16 operating days)</h3>
              <table className="tbl"><tbody>
                <tr><td>Planning value (50% gap capture)</td><td className={`num text-right ${tone(n(planning))}`}>{signed(n(planning))}</td></tr>
                <tr><td>Best case (zone’s best title)</td><td className={`num text-right ${tone(n(best))}`}>{signed(n(best))}</td></tr>
                {r && <>
                  <tr><td>Conservative (25% capture, 25% cannibalized)</td><td className={`num text-right ${tone(n(r["conservative_A10_0.25_cann_0.25"]))}`}>{signed(n(r["conservative_A10_0.25_cann_0.25"]))}</td></tr>
                  <tr><td>No revenue share on new lease (best)</td><td className={`num text-right ${tone(n(r.leaseclass_adjusted_best))}`}>{signed(n(r.leaseclass_adjusted_best))}</td></tr>
                  <tr><td>Ceiling +10% (best)</td><td className={`num text-right ${tone(n(r["best_with_ceiling_+10pct"]))}`}>{signed(n(r["best_with_ceiling_+10pct"]))}</td></tr>
                  <tr><td>July break-even gap capture</td><td className="num text-right">{pct(n(r.breakeven_A10_july), 0)}</td></tr>
                  <tr><td>Steady-state payback at 50%</td><td className="num text-right">{num(n(r["payback_days_after_install_at_A10_0.5"]))} days</td></tr>
                </>}
              </tbody></table>
              {r && <p className="mt-2 flex items-center gap-2 text-[12.5px]"><Pill tone={robustTone(String(r.robustness))}>{String(r.robustness).toLowerCase()}</Pill><span className="text-muted">{r.robustness === "ROBUST" ? "Negative in every tested variant." : r.robustness === "CONDITIONAL" ? "Negative at planning values; best case flips under some variants." : "Best case straddles zero."}</span></p>}
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
        <p className="label mt-1">A long line means the low total comes from floor time, location or luck rather than the machine. Select a row for detail.</p>
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
        <p className="label mt-1">Colored points are the manager’s 10 (color = verdict, also named in the table). Select a point for detail.</p>
      </Panel>
    </div>
  );
}
