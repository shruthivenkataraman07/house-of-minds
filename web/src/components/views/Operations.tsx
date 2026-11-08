"use client";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useApi } from "@/lib/api";
import { compact, n, num, pct, usd } from "@/lib/format";
import type { BankDetail, BankList, Comps, Demand, Downtime, Players } from "@/lib/types";
import { OFFICIAL, useUI } from "@/lib/ui";

import { ErrorLine, Kpi, Loading, PageHead, Panel, Pill, Scroll, Segmented, Tabs } from "../ui";

const AX = { stroke: "var(--muted)", fontSize: 11, tickLine: false, axisLine: false };
const TT = { contentStyle: { background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 12 } };
const ZCOL: Record<string, string> = { "Back Forty": "var(--chart-1)" };

export function Operations() {
  const ui = useUI();
  const tab = ui.tab ?? "demand";
  return (
    <div className="space-y-4">
      <PageHead title="Operations" line="Demand, downtime, tracked players and comps; totals are sums, ratios recomputed." />
      <Tabs label="Operations" value={tab} onChange={(t) => ui.set({ tab: t })} tabs={[
        { id: "demand", label: "Demand" }, { id: "banks", label: "Banks" }, { id: "downtime", label: "Downtime" },
        { id: "players", label: "Players" }, { id: "comps", label: "Comps" }]} />
      {(tab === "demand" || tab === "banks") && <PeriodControl />}
      {tab === "demand" && <DemandTab />}
      {tab === "banks" && <BanksTab />}
      {tab === "downtime" && <DowntimeTab />}
      {tab === "players" && <PlayersTab />}
      {tab === "comps" && <CompsTab />}
    </div>
  );
}

const PRESETS: [string, string, string][] = [["official", OFFICIAL.from, OFFICIAL.to], ["jan-apr", "2025-01-01", "2025-04-30"],
  ["may-jun", "2025-05-01", "2025-06-30"], ["q1", "2025-01-01", "2025-03-31"], ["q2", "2025-04-01", "2025-06-30"]];
const PLABEL: Record<string, string> = { official: "Jan–Jun", "jan-apr": "Jan–Apr", "may-jun": "May–Jun", q1: "Q1", q2: "Q2" };

function PeriodControl() {
  const ui = useUI();
  const cur = PRESETS.find(([, f, t]) => f === ui.period.from && t === ui.period.to)?.[0] ?? "custom";
  const exploratory = cur !== "official";
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Segmented label="Analysis period" value={cur} onChange={(id) => { const p = PRESETS.find((x) => x[0] === id)!; ui.set({ period: { from: p[1], to: p[2] } }); }}
        options={PRESETS.map(([id]) => ({ id, label: PLABEL[id] }))} />
      <label className="label">From <input type="date" min={OFFICIAL.from} max={OFFICIAL.to} value={ui.period.from} onChange={(e) => e.target.value && ui.set({ period: { ...ui.period, from: e.target.value } })} className="rounded border border-line bg-surface px-1 py-0.5 text-ink" /></label>
      <label className="label">To <input type="date" min={OFFICIAL.from} max={OFFICIAL.to} value={ui.period.to} onChange={(e) => e.target.value && ui.set({ period: { ...ui.period, to: e.target.value } })} className="rounded border border-line bg-surface px-1 py-0.5 text-ink" /></label>
      {exploratory ? <Pill tone="warn">Exploratory · verdicts stay on Jan–Jun</Pill> : <Pill>Official window</Pill>}
    </div>
  );
}

function DemandTab() {
  const { period } = useUI();
  const ok = period.from <= period.to;
  const { data, error, loading, reload } = useApi<Demand>(ok ? `/operations/demand?start=${period.from}&end=${period.to}` : null);
  if (!ok) return <p className="text-[13px] text-neg">Start date is after end date; adjust the period.</p>;
  if (error) return <ErrorLine error={error} retry={reload} />;
  if (!data) return <Loading rows={5} />;
  const d = data.data;
  const t = d.totals;
  const months = [...new Set(d.zone_monthly.map((r) => r.month))].sort();
  const zones = [...new Set(d.zone_monthly.map((r) => r.zone_name))];
  const zdata = months.map((mo) => Object.fromEntries([["month", mo], ...d.zone_monthly.filter((r) => r.month === mo).map((r) => [r.zone_name, r.theo_per_available_hour])]));
  const [e1, e2] = d.explanations;
  return (
    <div className={`space-y-4 ${loading ? "opacity-60" : ""}`}>
      <div className="panel grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 lg:grid-cols-5">
        <Kpi label="Coin-in" value={compact(t.coin_in_usd)} sub={`${t.days} gaming days`} />
        <Kpi label="Coin-in per day" value={compact(t.coin_in_per_day_usd)} />
        <Kpi label="Per available machine-hour" value={usd(t.coin_in_per_available_hour_usd, 2)} title="Separates demand from machine count" />
        <Kpi label="House win" value={compact(t.house_win_usd)} sub={`hold ${pct(t.hold, 2)}`} />
        <Kpi label="Theoretical win" value={compact(t.theo_usd)} sub={`theo hold ${pct(t.theo_hold, 2)}`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Weekly coin-in per day" note="Blue: per day · grey: per available machine-hour (right axis).">
          <div className="h-56" role="img" aria-label="Weekly coin-in per day and per available hour">
            <ResponsiveContainer><LineChart data={d.weekly} margin={{ left: 0, right: 0, top: 4 }}>
              <CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="week_start" {...AX} tickFormatter={(x: string) => x.slice(5)} minTickGap={24} />
              <YAxis yAxisId="a" {...AX} width={52} tickFormatter={(v: number) => compact(v)} />
              <YAxis yAxisId="b" orientation="right" {...AX} width={40} tickFormatter={(v: number) => `$${v.toFixed(0)}`} />
              <Tooltip {...TT} formatter={(v, k) => [k === "coin_in_per_day_usd" ? usd(Number(v)) : usd(Number(v), 2), k === "coin_in_per_day_usd" ? "Per day" : "Per avail. hour"]} />
              <Line isAnimationActive={false} yAxisId="a" dataKey="coin_in_per_day_usd" stroke="var(--chart-1)" dot={false} strokeWidth={2} />
              <Line isAnimationActive={false} yAxisId="b" dataKey="coin_in_per_available_hour_usd" stroke="var(--chart-2)" dot={false} strokeWidth={1.5} />
            </LineChart></ResponsiveContainer>
          </div>
        </Panel>
        <Panel title="Theo per available hour by zone" note="Monthly, official window; Back Forty highlighted.">
          <div className="h-56" role="img" aria-label="Zone theo per available hour by month">
            <ResponsiveContainer><LineChart data={zdata} margin={{ left: 0, right: 8, top: 4 }}>
              <CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="month" {...AX} /><YAxis {...AX} width={36} tickFormatter={(v: number) => `$${v}`} />
              <Tooltip {...TT} formatter={(v, k) => [usd(Number(v), 2), String(k)]} />
              {zones.map((z) => <Line isAnimationActive={false} key={z} dataKey={z} stroke={ZCOL[z] ?? "var(--chart-2)"} strokeOpacity={ZCOL[z] ? 1 : 0.55} dot={false} strokeWidth={ZCOL[z] ? 2.5 : 1.25} />)}
            </LineChart></ResponsiveContainer>
          </div>
        </Panel>
      </div>
      <Panel title="What changed and why" flush>
        <Scroll><table className="tbl min-w-[620px]"><thead><tr><th>Change</th><th className="text-right">Observed</th><th>Alternative tested</th><th>Result</th></tr></thead>
          <tbody>{[e1, e2].filter(Boolean).map((e, i) => (
            <tr key={i}><td>{String(e.change)}</td><td className="num text-right">{n(e.observed_pct).toFixed(1)}%</td>
              <td className="text-[12.5px] text-muted">{String(e.alternative)}</td><td className="text-[12.5px]">{String(e.conclusion)}</td></tr>))}</tbody></table></Scroll>
      </Panel>
      <p className="text-[13px]"><span className="font-medium">Action:</span> treat Back Forty as a location problem before blaming machines.</p>
    </div>
  );
}

function BanksTab() {
  const ui = useUI();
  const { period } = ui;
  const ok = period.from <= period.to;
  const z = ui.zoneId ? `&zone=${ui.zoneId}` : "";
  const list = useApi<BankList>(ok ? `/operations/banks?start=${period.from}&end=${period.to}${z}` : null);
  const det = useApi<BankDetail>(ok && ui.bankId ? `/operations/banks/${ui.bankId}?start=${period.from}&end=${period.to}` : null);
  if (!ok) return <p className="text-[13px] text-neg">Start date is after end date; adjust the period.</p>;
  if (list.error) return <ErrorLine error={list.error} retry={list.reload} />;
  if (!list.data) return <Loading rows={6} />;
  const b = det.data?.data;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel title="Banks by theo per available hour" note="All-play machine meters; hold = Σ house win / Σ coin-in." flush
        right={<select aria-label="Zone" value={ui.zoneId ?? ""} onChange={(e) => ui.set({ zoneId: e.target.value || null })} className="rounded border border-line bg-surface px-1.5 py-0.5 text-[12.5px]">
          <option value="">All zones</option>{["Z-B40", "Z-PIT", "Z-ENT", "Z-HL", "Z-BAR", "Z-GAR", "Z-HTL"].map((x) => <option key={x} value={x}>{x}</option>)}</select>}>
        <div className="max-h-[480px] overflow-auto">
          <table className="tbl min-w-[520px]"><thead><tr><th>Bank</th><th>Zone</th><th className="text-right">Coin-in</th><th className="text-right">House win</th><th className="text-right">Hold</th><th className="text-right">Theo / h</th></tr></thead>
            <tbody>{list.data.data.banks.map((r) => (
              <tr key={r.bank_id} className="row-click" aria-selected={ui.bankId === r.bank_id} onClick={() => ui.set({ bankId: r.bank_id })}>
                <td className="font-medium">{r.bank_id}</td><td className="text-[12.5px]">{r.zone_name}</td>
                <td className="num text-right">{compact(r.coin_in_usd)}</td><td className="num text-right">{compact(r.house_win_usd)}</td>
                <td className="num text-right">{pct(r.hold, 2)}</td><td className="num text-right">{usd(r.theo_per_available_hour_usd, 2)}</td></tr>))}</tbody></table>
        </div>
      </Panel>
      <Panel title={b ? `Bank ${b.bank_id}` : "Bank detail"} note={b ? `${b.totals.zone_name} · ${b.machines.length} machines · ${period.from} → ${period.to}` : "Select a bank."}>
        {det.error && <ErrorLine error={det.error} retry={det.reload} />}
        {ui.bankId && !b && !det.error && <Loading rows={4} />}
        {b && (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <Kpi label="Coin-in" value={compact(b.totals.coin_in_usd)} />
              <Kpi label="House win" value={compact(b.totals.house_win_usd)} sub={`hold ${pct(b.totals.hold, 2)}`} />
              <Kpi label="Theo" value={compact(b.totals.theo_usd)} sub={`${num(b.totals.machine_days)} machine-days`} />
            </div>
            <div className="h-48" role="img" aria-label={`Daily house win and theo for bank ${b.bank_id}`}>
              <ResponsiveContainer><LineChart data={b.daily} margin={{ left: 0, right: 0 }}><CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="gaming_date" {...AX} tickFormatter={(x: string) => x.slice(5)} minTickGap={28} /><YAxis {...AX} width={48} tickFormatter={(v: number) => compact(v)} />
                <Tooltip {...TT} formatter={(v, k) => [usd(Number(v)), k === "house_win_usd" ? "House win (actual)" : "Theo (expected)"]} />
                <Line isAnimationActive={false} dataKey="house_win_usd" stroke="var(--chart-2)" dot={false} />
                <Line isAnimationActive={false} dataKey="theo_usd" stroke="var(--chart-1)" dot={false} strokeWidth={1.75} />
              </LineChart></ResponsiveContainer>
            </div>
            <p className="label">Grey: actual house win (luck-driven) · blue: theoretical win.</p>
            <p className="flex flex-wrap gap-x-2 text-[12.5px]"><span className="label">Machines</span>{b.machines.map((m) => (
              <button key={m} type="button" onClick={() => ui.go("machines", { machineId: m })} className="text-accent hover:underline">{m}</button>))}</p>
          </div>
        )}
      </Panel>
    </div>
  );
}

function DowntimeTab() {
  const { data, error, reload } = useApi<Downtime>("/operations/downtime");
  if (error) return <ErrorLine error={error} retry={reload} />;
  if (!data) return <Loading rows={5} />;
  const d = data.data;
  const t = d.totals;
  const hours = d.by_hour.map((r) => ({ hour: `${String(r.local_hour).padStart(2, "0")}`, h: n(r.downtime_hours) }));
  return (
    <div className="space-y-4">
      <div className="panel grid grid-cols-2 gap-4 p-4 lg:grid-cols-4">
        <Kpi label="Downtime" value={`${num(t.downtime_hours)} h`} sub="machine-hours, Jan–Jun" />
        <Kpi label="Availability" value={pct(t.availability, 2)} />
        <Kpi label="Theo at risk" value={usd(t.theo_at_risk_usd)} sub="opportunity, not observed loss" />
        <Kpi label="Contribution at risk" value={usd(t.contribution_at_risk_usd)} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Downtime by local hour">
          <div className="h-52" role="img" aria-label="Downtime hours by local hour"><ResponsiveContainer><BarChart data={hours} margin={{ left: 0 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="hour" {...AX} interval={2} /><YAxis {...AX} width={36} />
            <Tooltip {...TT} formatter={(v) => [`${num(Number(v))} h`, "Downtime"]} />
            <Bar isAnimationActive={false} dataKey="h" fill="var(--chart-1)" radius={[2, 2, 0, 0]} /></BarChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="By manufacturer" flush>
          <Scroll><table className="tbl min-w-[440px]"><thead><tr><th>Manufacturer</th><th className="text-right">Down h</th><th className="text-right">Rate</th><th className="text-right">Faults</th><th className="text-right">Theo at risk</th></tr></thead>
            <tbody>{d.by_manufacturer.map((r) => <tr key={String(r.manufacturer)}><td>{String(r.manufacturer)}</td><td className="num text-right">{num(n(r.downtime_hours))}</td><td className="num text-right">{pct(n(r.downtime_rate), 2)}</td><td className="num text-right">{num(n(r.faults))}</td><td className="num text-right">{usd(n(r.theo_at_risk_usd))}</td></tr>)}</tbody></table></Scroll>
        </Panel>
      </div>
      <p className="text-[13px]"><span className="font-medium">Action:</span> target preventive maintenance at {String(d.by_manufacturer[0]?.manufacturer)} and evening technician coverage.</p>
    </div>
  );
}

function PlayersTab() {
  const ui = useUI();
  const { data, error, reload } = useApi<Players>("/players/summary");
  if (error) return <ErrorLine error={error} retry={reload} />;
  if (!data) return <Loading rows={5} />;
  const p = data.data.summary;
  const tiers = data.data.tiers;
  const totalTheo = tiers.reduce((s, x) => s + n(x.theo), 0);
  return (
    <div className="space-y-4">
      <p className="text-[12.5px] text-muted">Tracked (carded) play only: {pct(n(p.carded_share_of_all_coin_in))} of coin-in; never mixed with all-play meters.</p>
      <div className="panel grid grid-cols-2 gap-4 p-4 lg:grid-cols-4">
        <Kpi label="Tracked wagers" value={compact(n(p.tracked_coin_in_usd))} sub={`${num(n(p.players_with_tracked_play))} players`} />
        <Kpi label="Tracked payouts" value={compact(n(p.tracked_payout_usd))} />
        <Kpi label="Net player outcome" value={compact(n(p.tracked_player_net_usd))} className="text-neg" sub={`${pct(n(p.share_players_ahead))} finished ahead`} />
        <Kpi label="Top 10% share of theo" value={pct(n(p.top10pct_share_of_theo))} sub={`Gini ${n(p.gini_theo).toFixed(2)}`} />
      </div>
      <Panel title="By loyalty tier" note="Select a tier to drill in." flush>
        <Scroll><table className="tbl min-w-[600px]"><thead><tr><th>Tier</th><th className="text-right">Players</th><th className="text-right">Wagered</th><th className="text-right">Net (player)</th><th className="text-right">Theo</th><th className="text-right">Share of theo</th><th className="text-right">Ahead</th></tr></thead>
          <tbody>{tiers.map((t) => (
            <tr key={String(t.tier)} className="row-click" aria-selected={ui.tier === t.tier} onClick={() => ui.set({ tier: String(t.tier) })}>
              <td className="font-medium">{String(t.tier)}</td><td className="num text-right">{num(n(t.players))}</td><td className="num text-right">{compact(n(t.coin_in))}</td>
              <td className="num text-right text-neg">{compact(n(t.net))}</td><td className="num text-right">{compact(n(t.theo))}</td>
              <td className="num text-right">{pct(n(t.theo) / totalTheo)}</td><td className="num text-right">{pct(n(t.share_ahead))}</td></tr>))}</tbody></table></Scroll>
      </Panel>
      {ui.tier && (() => { const s = tiers.find((t) => t.tier === ui.tier); return s && <p className="text-[13px]">{String(s.tier)}: {num(n(s.players))} players wagered {usd(n(s.coin_in))}, net {usd(n(s.net))} (player view); {pct(n(s.share_ahead))} finished ahead.</p>; })()}
    </div>
  );
}

function CompsTab() {
  const { data, error, reload } = useApi<Comps>("/loyalty/comps");
  if (error) return <ErrorLine error={error} retry={reload} />;
  if (!data) return <Loading rows={5} />;
  const rows = data.data.months.map((r) => ({ month: String(r.month), ppd: n(r.points_per_comp_usd), cost: n(r.comp_cost_usd), rate: n(r.comp_cost_per_carded_theo), awarded: n(r.points_awarded), redeemed: n(r.points_redeemed) }));
  const f = rows[0], l = rows[rows.length - 1];
  return (
    <div className="space-y-4">
      <div className="panel grid grid-cols-2 gap-4 p-4 lg:grid-cols-4">
        <Kpi label="Points awarded" value={num(rows.reduce((s, r) => s + r.awarded, 0))} />
        <Kpi label="Points redeemed" value={num(rows.reduce((s, r) => s + r.redeemed, 0))} />
        <Kpi label="Comp cost" value={usd(rows.reduce((s, r) => s + r.cost, 0))} sub="economic cost, counted once" />
        <Kpi label="Cost per carded theo" value={`${pct(f.rate, 2)} → ${pct(l.rate, 2)}`} sub={`${f.month} → ${l.month}`} />
      </div>
      <Panel title="Points per comp dollar" note={`${f.ppd.toFixed(1)} in ${f.month} → ${l.ppd.toFixed(1)} in ${l.month}; change effective May 1, 2025.`}>
        <div className="h-52" role="img" aria-label="Points per comp dollar by month"><ResponsiveContainer><BarChart data={rows} margin={{ left: 0 }}>
          <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="month" {...AX} /><YAxis {...AX} width={32} />
          <Tooltip {...TT} formatter={(v) => [Number(v).toFixed(1), "Points per $"]} />
          <Bar isAnimationActive={false} dataKey="ppd" fill="var(--chart-1)" radius={[2, 2, 0, 0]} /></BarChart></ResponsiveContainer></div>
      </Panel>
      <p className="text-[13px]"><span className="font-medium">Action:</span> treat the change as a cost increase until a holdout pilot shows incremental play.</p>
    </div>
  );
}
