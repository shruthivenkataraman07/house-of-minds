"use client";
import { type ReactNode, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useApi } from "@/lib/api";
import { compact, n, num, pct, usd } from "@/lib/format";
import { TERM } from "@/lib/terms";
import type { BankDetail, BankList, Comps, Demand, Downtime, Events, EvidenceList, Players } from "@/lib/types";
import { OFFICIAL, useUI } from "@/lib/ui";

import { CalendarHeat, CompositionBar, MatrixHeat } from "../charts";
import { F } from "@/lib/formulas";
import { How, Term } from "../explain";
import { Drawer, ErrorLine, EvidenceLink, Kpi, Loading, PageHead, Panel, Pill, Scroll, Segmented, Tabs } from "../ui";

const AX = { stroke: "var(--muted)", fontSize: 11, tickLine: false, axisLine: false };
const TT = { contentStyle: { background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 12 } };

export function Operations() {
  const ui = useUI();
  const tab = ui.tab === "banks" ? "demand" : ui.tab ?? "demand"; // banks live inside Demand
  return (
    <div className="space-y-4">
      <PageHead title="Operations" line="What happened, how much, and why it matters, for four operating questions." />
      <Tabs label="Operations" value={tab} onChange={(t) => ui.set({ tab: t })} tabs={[
        { id: "demand", label: "Demand" }, { id: "downtime", label: "Downtime" },
        { id: "players", label: "Players" }, { id: "comps", label: "Comps" }]} />
      {tab === "demand" && <PeriodControl />}
      {tab === "demand" && <DemandTab />}
      {tab === "demand" && <BanksTab />}
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
  const [day, setDay] = useState<string | null>(null);
  const [zoneSel, setZoneSel] = useState<string | null>(null);
  const ok = period.from <= period.to;
  const { data, error, loading, reload } = useApi<Demand>(ok ? `/operations/demand?start=${period.from}&end=${period.to}` : null);
  if (!ok) return <p className="text-[13px] text-neg">Start date is after end date; adjust the period.</p>;
  if (error) return <ErrorLine error={error} retry={reload} />;
  if (!data || data.data.period.start !== period.from || data.data.period.end !== period.to) {
    return <div aria-busy="true"><p className="label mb-2">Loading {period.from} → {period.to}…</p><Loading rows={5} /></div>;
  }
  if (data.data.totals.days === 0) return <p className="panel p-4 text-[13px] text-muted">No gaming days in {period.from} → {period.to}; choose another period.</p>;
  const d = data.data;
  const t = d.totals;
  const months = [...new Set(d.zone_monthly.map((r) => r.month))].sort();
  const zoneIds = [...new Set(d.zone_monthly.map((r) => r.zone_id))];
  const zname = (z: string) => d.zone_monthly.find((r) => r.zone_id === z)?.zone_name ?? z;
  const zval = (z: string, mo: string) => d.zone_monthly.find((r) => r.zone_id === z && r.month === mo)?.theo_per_available_hour ?? null;
  const avgDay = t.days ? t.coin_in_usd / t.days : 0;
  const dsel = d.daily.find((r) => r.gaming_date === day);
  return (
    <div className={`space-y-4 ${loading ? "opacity-60" : ""}`}>
      <div className="panel grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 lg:grid-cols-5">
        <Kpi label={<Term id="wagered" />} value={compact(t.coin_in_usd)} sub={`over ${t.days} gaming days`} />
        <Kpi label="Wagered per day" value={compact(t.coin_in_per_day_usd)} sub="the period’s daily average" />
        <Kpi label={<>Wagered per <Term id="machine_hour">machine-hour</Term></>} value={usd(t.coin_in_per_available_hour_usd, 2)} sub="demand with machine count removed" />
        <Kpi label={<Term id="casino_win" />} value={compact(t.house_win_usd)} sub={`kept ${pct(t.hold, 2)} of every dollar bet`} />
        <Kpi label={<Term id="expected_win" />} value={compact(t.theo_usd)} sub={`games are designed to keep ${pct(t.theo_hold, 2)}`} />
      </div>
      <How steps={[
        <>We add up every gaming day in the period ({t.days} days, each running 6 a.m. to 6 a.m.).</>,
        <>“Wagered per machine-hour” divides the total bet by the hours machines were switched on and playable. If this falls, each machine was played less: it is not just that some machines were missing.</>,
        <>The share kept is total casino win divided by total wagered, worked out once over the whole period rather than averaging daily percentages, so busy days count more than quiet ones.</>,
        <>Expected casino win removes payout luck: it is what the games are built to keep on the amount bet. When casino win and expected win differ, the difference is luck.</>,
      ]} technical="Ratio of sums over property_day (integer cents); available hours from machine meters."
        formulas={[F.casinoWin(), F.expectedWin(), F.perHour()]} />
      <Panel title="When was the floor busy?" note={`Daily amount wagered, ${period.from} → ${period.to}; amber outline = event day. Select a day for detail.`}>
        <CalendarHeat label="Daily amount wagered calendar" format={(v) => usd(v)} selected={day} onDay={setDay}
          days={d.daily.map((r) => ({ date: r.gaming_date, value: r.coin_in_usd, flag: !!r.events }))} />
      </Panel>
      {dsel && (
        <Drawer label={`Gaming day ${dsel.gaming_date}`} onClose={() => setDay(null)} title={<><span className="label block">Gaming day (6 a.m.–6 a.m.)</span>{new Date(`${dsel.gaming_date}T00:00:00Z`).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: "UTC" })}</>}>
          <div className="grid grid-cols-2 gap-4">
            <Kpi label={TERM.coin_in} value={usd(dsel.coin_in_usd)} sub={`${dsel.coin_in_usd >= avgDay ? "+" : "−"}${pct(Math.abs(dsel.coin_in_usd / avgDay - 1))} vs period daily average`} />
            <Kpi label={TERM.house_win} value={usd(dsel.house_win_usd)} sub={`${TERM.hold.toLowerCase()} ${pct(dsel.hold, 2)}`} />
            <Kpi label={TERM.theo} value={usd(dsel.theo_usd)} />
            <Kpi label="Machines active" value={num(dsel.active_machines)} sub={`${num(dsel.available_hours)} available machine-hours`} />
          </div>
          <p className="mt-4 text-[13px]"><span className="text-muted">Events: </span>{dsel.events ?? "none recorded"}</p>
          <p className="label mt-2">Source: property_day (sidecar daily grain). Casino win varies with payout luck; expected win does not.</p>
        </Drawer>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Is weekly demand trending down?" note={`Average ${TERM.coin_in.toLowerCase()} per gaming day, by week (partial weeks averaged over their own days).`}>
          <div className="h-56" role="img" aria-label="Weekly amount wagered per day">
            <ResponsiveContainer><LineChart data={d.weekly} margin={{ left: 0, right: 0, top: 4 }}>
              <CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="week_start" {...AX} tickFormatter={(x: string) => x.slice(5)} minTickGap={24} />
              <YAxis yAxisId="a" {...AX} width={52} tickFormatter={(v: number) => compact(v)} />
              <Tooltip {...TT} formatter={(v) => [usd(Number(v)), "Wagered per day"]} labelFormatter={(l) => `Week of ${String(l)}`} />
              <Line isAnimationActive={false} yAxisId="a" dataKey="coin_in_per_day_usd" stroke="var(--chart-1)" dot={false} strokeWidth={2} />
            </LineChart></ResponsiveContainer>
          </div>
          <How steps={["Each point is one week: the total amount wagered that week divided by the number of gaming days in it.", "Weeks cut off by the start or end of your period use only the days inside it, so a short week is not undercounted."]} />
        </Panel>
        <Panel title="Which zones lost demand, and when?" note={`${TERM.theo_per_hour} by zone and month (official window). Select a zone.`}>
          <MatrixHeat label="Expected win per available hour by zone and month" format={(v) => `$${v.toFixed(1)}`} selectedRow={zoneSel}
            rows={zoneIds.map((z) => ({ key: z, label: zname(z) }))} cols={months.map((m) => ({ key: m, label: new Date(`${m}-01T00:00:00Z`).toLocaleString("en-US", { month: "short", timeZone: "UTC" }) }))}
            value={zval} onCell={(z) => setZoneSel(z)} />
          <How steps={[
            "Each cell is the zone’s expected casino win for that month, divided by the hours its machines were switched on.",
            "Expected win removes payout luck, and dividing by hours removes the effect of machines being broken or moved, so cells compare how busy each zone really was.",
            "Darker means more expected win per machine-hour. Back Forty’s pale March is the walkway closure (see below).",
          ]} />
        </Panel>
      </div>
      {zoneSel && <ZoneDrawer zone={zoneSel} name={zname(zoneSel)} months={months} value={zval} explanations={d.explanations} onClose={() => setZoneSel(null)} />}
      <EventPanel onZone={() => setZoneSel("Z-B40")} />
      <Panel title="What changed, and is there another explanation?" note={d.comparison ? "The first finding follows the period you picked; the other two are the official Jan–Jun findings and stay fixed." : "Official Jan–Jun findings. Pick a shorter period above to compare it with the rest of the six months."}>
        <div className="grid gap-3 lg:grid-cols-3">
          {d.comparison && (() => {
            const c = d.comparison; const up = c.wagered_per_day_change_pct >= 0;
            const sameWay = c.wagered_per_day_change_pct * c.wagered_per_available_hour_change_pct > 0;
            return (
              <Finding tag="Your period" highlight
                what={<>Daily wagers in {c.selected.replace("..", " to ")} were <b>{Math.abs(c.wagered_per_day_change_pct).toFixed(1)}% {up ? "higher" : "lower"}</b> than in the rest of January–June.</>}
                alt="Maybe more or fewer machines were running, rather than guests betting differently."
                found={Math.abs(c.wagered_per_day_change_pct) < 1
                  ? <>Little real change: the difference is under 1%.</>
                  : sameWay
                    ? <>Not just machine count: wagers per <Term id="machine_hour">machine-hour</Term> also moved {c.wagered_per_available_hour_change_pct >= 0 ? "up" : "down"} {Math.abs(c.wagered_per_available_hour_change_pct).toFixed(1)}%, so each machine was played {c.wagered_per_available_hour_change_pct >= 0 ? "more" : "less"}.</>
                    : <>Mostly machine count: per machine-hour, wagers moved the other way ({c.wagered_per_available_hour_change_pct >= 0 ? "+" : "−"}{Math.abs(c.wagered_per_available_hour_change_pct).toFixed(1)}%).</>}
                how={[`We compare your ${c.selected_days} days with the other ${c.comparison_days} days of January–June.`, "First, total wagered per day. Then total wagered per hour that machines were switched on.", "If both move the same way, guests really bet more or less; if only the daily total moves, the number of machines changed."]} />);
          })()}
          {(() => {
            const e = d.explanations.find((x) => /May-Jun/i.test(String(x.change)));
            if (!e) return null;
            return (
              <Finding tag="Official finding"
                what={<>In May–June, guests wagered <b>{Math.abs(n(e.observed_pct)).toFixed(1)}% less per day</b> than in January–April.</>}
                alt="Maybe fewer machines were running in May–June."
                found={<>No: wagers per <Term id="machine_hour">machine-hour</Term> fell {Math.abs(n(e.result_pct)).toFixed(1)}%, even more than the daily total. Each machine was played less, so demand itself softened.</>}
                how={["Total wagered ÷ days, for January–April and for May–June.", "Then total wagered ÷ hours machines were switched on, for both periods.", "The per-hour drop is at least as large as the daily drop, so missing machines cannot be the reason."]} />);
          })()}
          {(() => {
            const e = d.explanations.find((x) => /walkway/i.test(String(x.change)));
            if (!e) return null;
            const ci = String(e.conclusion).match(/\[(-?[\d.]+),\s*(-?[\d.]+)\]/);
            const rec = String(e.conclusion).match(/\((-?[\d.]+)%\)/);
            return (
              <Finding tag="Official finding"
                what={<>While the walkway into Back Forty was closed (Mar 3–Apr 6), Back Forty earned <b>{Math.abs(n(e.observed_pct)).toFixed(1)}% less</b> than the rest of the casino would suggest.</>}
                alt="Maybe the whole casino was in a seasonal dip at the time."
                found={<>No: the rest of the floor held steady.{ci ? <> We are 95% confident the true drop was between {Math.abs(Number(ci[2])).toFixed(1)}% and {Math.abs(Number(ci[1])).toFixed(1)}% (<Term id="ci">confidence range</Term>).</> : null}{rec ? <> After reopening, Back Forty was back to within {Math.abs(Number(rec[1])).toFixed(1)}% of normal.</> : null}</>}
                how={["We use only machines that stayed in one zone for all six months, so moves and new machines cannot create the effect.", "Each day, we compare Back Forty’s expected win per machine-hour with the rest of the casino’s.", "We compare that gap before, during and after the closure, allowing for normal weekday patterns.", "It is one event, so this is strong evidence of an effect, not absolute proof."]}
                technical="Log ratio regression with weekday effects and closure/post indicators; Newey-West (HAC, 7 lags) errors." />);
          })()}
        </div>
      </Panel>
      <p className="text-[14px]"><span className="font-semibold">What to do:</span> treat Back Forty as a location and foot-traffic problem before blaming its machines.</p>
    </div>
  );
}

function Finding({ tag, what, alt, found, how, technical, highlight = false }: {
  tag: string; what: ReactNode; alt: ReactNode; found: ReactNode; how: ReactNode[]; technical?: string; highlight?: boolean;
}) {
  return (
    <article className={`flex flex-col rounded-lg border p-4 ${highlight ? "border-accent/40 bg-accent-soft" : "border-line bg-surface"}`}>
      <p className="label">{tag}</p>
      <p className="mt-1 text-[14.5px] leading-snug">{what}</p>
      <dl className="mt-3 space-y-2 text-[13.5px] leading-relaxed">
        <div><dt className="text-[12px] font-medium uppercase tracking-wide text-muted">Could something else explain it?</dt><dd>{alt}</dd></div>
        <div><dt className="text-[12px] font-medium uppercase tracking-wide text-muted">What the data says</dt><dd>{found}</dd></div>
      </dl>
      <div className="mt-auto"><How steps={how} technical={technical} /></div>
    </article>
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
  if (!list.data || list.data.data.period.start !== period.from || list.data.data.period.end !== period.to) return <Loading rows={6} />;
  const b = det.data?.data;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel title="Which banks of machines earn least?" note="A bank is a group of machines standing together. Ranked by expected win per machine-hour, weakest first. Select one to see its days and machines." flush
        right={<select aria-label="Zone" value={ui.zoneId ?? ""} onChange={(e) => ui.set({ zoneId: e.target.value || null })} className="rounded border border-line bg-surface px-1.5 py-0.5 text-[12.5px]">
          <option value="">All zones</option>{["Z-B40", "Z-PIT", "Z-ENT", "Z-HL", "Z-BAR", "Z-GAR", "Z-HTL"].map((x) => <option key={x} value={x}>{x}</option>)}</select>}>
        <div className="max-h-[480px] overflow-auto">
          <table className="tbl min-w-[520px]"><thead><tr><th>Bank</th><th>Zone</th><th className="text-right">Wagered</th><th className="text-right">Casino win</th><th className="text-right" title="Casino win ÷ amount wagered, over the whole period">Share kept</th><th className="text-right" title="Expected casino win ÷ hours machines were switched on">Expected win / machine-hour</th></tr></thead>
            <tbody>{list.data.data.banks.map((r) => (
              <tr key={r.bank_id} className="row-click" aria-selected={ui.bankId === r.bank_id} onClick={() => ui.set({ bankId: r.bank_id })}>
                <td className="font-medium">{r.bank_id}</td><td className="text-[12.5px]">{r.zone_name}</td>
                <td className="num text-right">{compact(r.coin_in_usd)}</td><td className="num text-right">{compact(r.house_win_usd)}</td>
                <td className="num text-right">{pct(r.hold, 2)}</td><td className="num text-right">{usd(r.theo_per_available_hour_usd, 2)}</td></tr>))}</tbody></table>
        </div>
      </Panel>
      <Panel title={b ? `Bank ${b.bank_id}` : "Bank detail"} note={b ? `${b.totals.zone_name} · ${b.machines.length} machines · ${period.from} → ${period.to}` : "Pick a bank in the list to see its daily earnings and its machines."}>
        {det.error && <ErrorLine error={det.error} retry={det.reload} />}
        {ui.bankId && !b && !det.error && <Loading rows={4} />}
        {b && (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <Kpi label="Wagered" value={compact(b.totals.coin_in_usd)} />
              <Kpi label="Casino win" value={compact(b.totals.house_win_usd)} sub={`share kept ${pct(b.totals.hold, 2)}`} />
              <Kpi label="Expected win" value={compact(b.totals.theo_usd)} sub={`${num(b.totals.machine_days)} machine-days`} />
            </div>
            <div className="h-48" role="img" aria-label={`Daily house win and theo for bank ${b.bank_id}`}>
              <ResponsiveContainer><LineChart data={b.daily} margin={{ left: 0, right: 0 }}><CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="gaming_date" {...AX} tickFormatter={(x: string) => x.slice(5)} minTickGap={28} /><YAxis {...AX} width={48} tickFormatter={(v: number) => compact(v)} />
                <Tooltip {...TT} formatter={(v, k) => [usd(Number(v)), k === "house_win_usd" ? "Casino win (actual)" : "Expected casino win"]} />
                <Line isAnimationActive={false} dataKey="house_win_usd" stroke="var(--chart-2)" dot={false} />
                <Line isAnimationActive={false} dataKey="theo_usd" stroke="var(--chart-1)" dot={false} strokeWidth={1.75} />
              </LineChart></ResponsiveContainer>
            </div>
            <p className="label">Grey: actual casino win (varies with payout luck) · blue: expected casino win.</p>
            <p className="flex flex-wrap gap-x-2 text-[12.5px]"><span className="label">Machines</span>{b.machines.map((m) => (
              <button key={m} type="button" onClick={() => ui.go("machines", { machineId: m })} className="text-accent hover:underline">{m}</button>))}</p>
          </div>
        )}
      </Panel>
    </div>
  );
}

function DowntimeTab() {
  const [zsel, setZsel] = useState<string | null>(null);
  const { data, error, reload } = useApi<Downtime>("/operations/downtime");
  if (error) return <ErrorLine error={error} retry={reload} />;
  if (!data) return <Loading rows={5} />;
  const d = data.data;
  const t = d.totals;
  const hours = d.by_hour.map((r) => ({ hour: `${String(r.local_hour).padStart(2, "0")}`, h: n(r.downtime_hours) }));
  const zm = d.by_zone_month;
  const zones = [...new Set(zm.map((r) => String(r.zone_id)))];
  const zn = (z: string) => String(zm.find((r) => r.zone_id === z)?.zone_name ?? z);
  const mos = [...new Set(zm.map((r) => String(r.month)))].sort();
  const cell = (z: string, mo: string) => {
    const rs = zm.filter((r) => r.zone_id === z && r.month === mo);
    return rs.length ? rs.reduce((s2, r) => s2 + n(r.downtime_hours), 0) : null;
  };
  const zRows = zsel ? zm.filter((r) => r.zone_id === zsel) : [];
  const byMfr = Object.values(zRows.reduce<Record<string, { m: string; h: number; risk: number; contrib: number; faults: number }>>((a, r) => {
    const k = String(r.manufacturer); const e = a[k] ?? { m: k, h: 0, risk: 0, contrib: 0, faults: 0 };
    e.h += n(r.downtime_hours); e.risk += n(r.theo_at_risk_usd); e.contrib += n(r.contribution_at_risk_usd); e.faults += n(r.faults); a[k] = e; return a;
  }, {})).sort((a, b) => b.h - a.h);
  return (
    <div className="space-y-4">
      <div className="panel grid grid-cols-2 gap-4 p-4 lg:grid-cols-4">
        <Kpi label={`${TERM.downtime} (actual)`} value={`${num(t.downtime_hours)} h`} sub="machine-hours, Jan–Jun" />
        <Kpi label={TERM.availability} value={pct(t.availability, 2)} />
        <Kpi label={`${TERM.theo_at_risk} (modeled)`} value={usd(t.theo_at_risk_usd)} sub="opportunity, not observed loss" />
        <Kpi label="Contribution at risk" value={usd(t.contribution_at_risk_usd)} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Where and when were machines unavailable?" note="Actual downtime hours by zone and month. Select a zone for its breakdown." className="lg:col-span-2">
          <MatrixHeat label="Downtime hours by zone and month" format={(v) => num(v)} selectedRow={zsel}
            rows={zones.map((z) => ({ key: z, label: zn(z) }))} cols={mos.map((m) => ({ key: m, label: new Date(`${m}-01T00:00:00Z`).toLocaleString("en-US", { month: "short", timeZone: "UTC" }) }))}
            value={cell} onCell={(z) => setZsel(z)} />
          <p className="label mt-1">Downtime is not exported by bank; zone × month is the finest verified grain.</p>
        </Panel>
        <Panel title="When in the day are machines down?" note="Actual downtime hours by local hour.">
          <div className="h-52" role="img" aria-label="Downtime hours by local hour"><ResponsiveContainer><BarChart data={hours} margin={{ left: 0 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="hour" {...AX} interval={2} /><YAxis {...AX} width={36} />
            <Tooltip {...TT} formatter={(v) => [`${num(Number(v))} h`, "Downtime"]} />
            <Bar isAnimationActive={false} dataKey="h" fill="var(--chart-1)" radius={[2, 2, 0, 0]} /></BarChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="By manufacturer" flush>
          <Scroll><table className="tbl min-w-[440px]"><thead><tr><th>Manufacturer</th><th className="text-right">Down h</th><th className="text-right">Rate</th><th className="text-right">Faults</th><th className="text-right">Expected win at risk</th></tr></thead>
            <tbody>{d.by_manufacturer.map((r) => <tr key={String(r.manufacturer)}><td>{String(r.manufacturer)}</td><td className="num text-right">{num(n(r.downtime_hours))}</td><td className="num text-right">{pct(n(r.downtime_rate), 2)}</td><td className="num text-right">{num(n(r.faults))}</td><td className="num text-right">{usd(n(r.theo_at_risk_usd))}</td></tr>)}</tbody></table></Scroll>
        </Panel>
      </div>
      {zsel && (
        <Drawer label={`Downtime in ${zn(zsel)}`} onClose={() => setZsel(null)} title={<><span className="label block">Downtime breakdown · Jan–Jun</span>{zn(zsel)}</>}>
          <div className="grid grid-cols-2 gap-4">
            <Kpi label="Actual downtime" value={`${num(byMfr.reduce((a, r) => a + r.h, 0))} h`} sub={`${pct(byMfr.reduce((a, r) => a + r.h, 0) / t.downtime_hours)} of floor downtime`} />
            <Kpi label={`${TERM.theo_at_risk} (modeled)`} value={usd(byMfr.reduce((a, r) => a + r.risk, 0))} sub="if lost play did not move elsewhere" />
          </div>
          <table className="tbl mt-4"><thead><tr><th>Manufacturer</th><th className="text-right">Down h</th><th className="text-right">Faults</th><th className="text-right">Win at risk</th></tr></thead>
            <tbody>{byMfr.map((r) => <tr key={r.m}><td>{r.m}</td><td className="num text-right">{num(r.h)}</td><td className="num text-right">{num(r.faults)}</td><td className="num text-right">{usd(r.risk)}</td></tr>)}</tbody></table>
          <p className="label mt-3">Hours are observed meter downtime; win at risk is a modeled opportunity, not realized loss.</p>
        </Drawer>
      )}
      <How steps={[
        "Downtime hours: for every machine and day, the hours it was scheduled to be available minus the hours it actually was, from the machine’s own meters.",
        <>Expected win at risk: each lost hour × what that machine normally earns per available hour (<Term id="expected_win">expected win</Term>).</>,
        <>Contribution at risk: the same, after revenue share and loyalty costs (<Term id="contribution" />).</>,
        "This is an upper estimate of the opportunity: some guests simply move to a nearby machine, so the real loss is likely smaller.",
      ]} formulas={[F.downtime(t.downtime_hours, t.theo_at_risk_usd)]} />
      <p className="text-[14px]"><span className="font-semibold">What to do:</span> target preventive maintenance at {String(d.by_manufacturer[0]?.manufacturer)} and technician coverage near {(() => { const pk = [...d.by_hour].sort((a, b) => n(b.downtime_hours) - n(a.downtime_hours))[0]; return pk ? `${String(pk.local_hour).padStart(2, "0")}:00` : "peak hours"; })()}, the worst downtime hour.</p>
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
        <Kpi label="Top 10% share of expected win" value={pct(n(p.top10pct_share_of_theo))} sub={`Gini ${n(p.gini_theo).toFixed(2)}`} />
      </div>
      <Panel title="How concentrated is tracked play?" note="Share of tracked expected win by player group (aggregate shares; no individual records).">
        <CompositionBar label="Share of tracked expected win by player group" segments={[
          { key: "top1", label: "Top 1% of players", value: Math.round(n(p.top1pct_share_of_theo) * 1000) / 10, display: pct(n(p.top1pct_share_of_theo)), tone: "accent" },
          { key: "next9", label: "Next 9%", value: Math.round((n(p.top10pct_share_of_theo) - n(p.top1pct_share_of_theo)) * 1000) / 10, display: pct(n(p.top10pct_share_of_theo) - n(p.top1pct_share_of_theo)), tone: "warn" },
          { key: "rest", label: "Other 90%", value: Math.round((1 - n(p.top10pct_share_of_theo)) * 1000) / 10, display: pct(1 - n(p.top10pct_share_of_theo)), tone: "muted" }]} />
      </Panel>
      <How steps={[
        <>Only <Term id="tracked">tracked play</Term> is included: guests who used a loyalty card.</>,
        "Net player outcome = what tracked guests were paid out minus what they bet. Negative means guests lost that amount in total.",
        "Concentration: we rank tracked guests by their expected casino win and add up the top 1% and top 10%.",
        <>The Gini score runs from 0 (everyone plays the same) to 1 (one guest does all the play); {n(p.gini_theo).toFixed(2)} means play is heavily concentrated.</>,
        "Only group totals are shown. No individual guest can be identified.",
      ]} formulas={[F.gini(n(p.gini_theo))]} />
      <Panel title="By loyalty tier" note="Select a tier to drill in." flush>
        <Scroll><table className="tbl min-w-[600px]"><thead><tr><th>Tier</th><th className="text-right">Players</th><th className="text-right">Wagered</th><th className="text-right">Net (player view)</th><th className="text-right">Expected win</th><th className="text-right">Share of theo</th><th className="text-right">Ahead</th></tr></thead>
          <tbody>{tiers.map((t) => (
            <tr key={String(t.tier)} className="row-click" aria-selected={ui.tier === t.tier} onClick={() => ui.set({ tier: String(t.tier) })}>
              <td className="font-medium">{String(t.tier)}</td><td className="num text-right">{num(n(t.players))}</td><td className="num text-right">{compact(n(t.coin_in))}</td>
              <td className="num text-right text-neg">{compact(n(t.net))}</td><td className="num text-right">{compact(n(t.theo))}</td>
              <td className="num text-right">{pct(n(t.theo) / totalTheo)}</td><td className="num text-right">{pct(n(t.share_ahead))}</td></tr>))}</tbody></table></Scroll>
      </Panel>
      <p className="text-[13px]"><span className="font-medium">Why it matters:</span> play is concentrated, so program design should use tier economics, never individual targeting.</p>
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
        <Kpi label="Cost per tracked expected win" value={`${pct(f.rate, 2)} → ${pct(l.rate, 2)}`} sub={`${f.month} → ${l.month}`} />
      </div>
      <How steps={[
        "Points per comp dollar = loyalty points guests redeemed ÷ the menu value of the comps they received. Fewer points per dollar means rewards became cheaper for guests to get.",
        "Comp cost is what the rewards actually cost the casino (not their menu price), counted once.",
        <>Cost per tracked expected win = comp cost ÷ the <Term id="expected_win">expected win</Term> from tracked guests: how much of each expected dollar is given back as rewards.</>,
        "We cannot tell whether the cheaper rewards brought in extra play: there was no comparison group, and demand also softened.",
      ]} formulas={[F.comps()]} />
      <Panel title="How many points buy a dollar of rewards?" note={`${f.ppd.toFixed(1)} points in ${f.month} → ${l.ppd.toFixed(1)} in ${l.month}; the change took effect May 1, 2025.`}>
        <div className="h-52" role="img" aria-label="Points per comp dollar by month"><ResponsiveContainer><BarChart data={rows} margin={{ left: 0 }}>
          <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="month" {...AX} /><YAxis {...AX} width={32} />
          <Tooltip {...TT} formatter={(v) => [Number(v).toFixed(1), "Points per $"]} />
          <Bar isAnimationActive={false} dataKey="ppd" fill="var(--chart-1)" radius={[2, 2, 0, 0]} /></BarChart></ResponsiveContainer></div>
      </Panel>
      <p className="text-[14px]"><span className="font-semibold">What to do:</span> treat the change as a cost increase until a holdout pilot shows incremental play.</p>
    </div>
  );
}

function ZoneDrawer({ zone, name, months, value, explanations, onClose }: {
  zone: string; name: string; months: string[]; value: (z: string, m: string) => number | null;
  explanations: Demand["explanations"]; onClose: () => void;
}) {
  const ui = useUI();
  const banks = useApi<BankList>(`/operations/banks?zone=${zone}`);
  const ev = useApi<EvidenceList>("/evidence?category=zone_demand");
  const related = explanations.filter((e) => String(e.change).toLowerCase().includes(name.toLowerCase()));
  const first = value(zone, months[0]), last = value(zone, months[months.length - 1]);
  const claim = ev.data?.data.claims[0]?.claim_id;
  return (
    <Drawer label={`Zone ${name}`} onClose={onClose} title={<><span className="label block">Zone · official window</span>{name}</>}>
      <div className="grid grid-cols-2 gap-4">
        <Kpi label={`${TERM.theo_per_hour} · ${months[0]}`} value={first === null ? "—" : usd(first, 2)} />
        <Kpi label={`… · ${months[months.length - 1]}`} value={last === null ? "—" : usd(last, 2)} sub={first && last ? `${last >= first ? "+" : "−"}${pct(Math.abs(last / first - 1))} over the window` : undefined} />
      </div>
      <table className="tbl mt-4"><thead><tr><th>Month</th><th className="text-right">{TERM.theo_per_hour}</th></tr></thead>
        <tbody>{months.map((m) => <tr key={m}><td>{m}</td><td className="num text-right">{value(zone, m) === null ? "—" : usd(value(zone, m), 2)}</td></tr>)}</tbody></table>
      {related.map((e, i) => <p key={i} className="mt-3 text-[13px]"><span className="font-medium">{String(e.change)}:</span> {n(e.observed_pct).toFixed(1)}% · {String(e.conclusion)}</p>)}
      <h3 className="mt-4 text-[12.5px] font-semibold">Banks in this zone</h3>
      {banks.data ? (
        <p className="mt-1 flex flex-wrap gap-x-2 text-[12.5px]">{banks.data.data.banks.map((b) => (
          <button key={b.bank_id} type="button" onClick={() => { onClose(); ui.set({ zoneId: zone, bankId: b.bank_id }); }} className="text-accent hover:underline">{b.bank_id}</button>))}</p>
      ) : <Loading rows={1} />}
      <div className="mt-4 border-t border-line pt-3">{claim ? <EvidenceLink id={String(claim)}>Zone demand evidence</EvidenceLink> : <span className="label">No zone evidence record.</span>}</div>
    </Drawer>
  );
}

/** Walkway closure: Back Forty vs rest of floor on a fixed machine set (API: /operations/events). */
function EventPanel({ onZone }: { onZone: () => void }) {
  const { data, error, reload } = useApi<Events>("/operations/events");
  if (error) return <ErrorLine error={error} retry={reload} />;
  if (!data) return <Loading rows={2} />;
  const e = data.data;
  return (
    <Panel title="Did the walkway closure cut Back Forty demand?" note={`Always Jan–Jun (event study, not affected by the period filter). ${e.event}, ${e.closed_from} → ${e.closed_to} (shaded); ${e.unit}.`}
      right={<button type="button" onClick={onZone} className="text-[12.5px] text-accent hover:underline">Back Forty detail →</button>}>
      <div className="h-56" role="img" aria-label="Daily expected win per available hour, Back Forty versus rest of floor, with the closure period shaded">
        <ResponsiveContainer><LineChart data={e.rows} margin={{ left: 0, right: 8, top: 4 }}>
          <CartesianGrid stroke="var(--line)" vertical={false} />
          <XAxis dataKey="gaming_date" {...AX} tickFormatter={(x: string) => x.slice(5)} minTickGap={28} />
          <YAxis {...AX} width={40} tickFormatter={(v: number) => `$${v.toFixed(0)}`} />
          <ReferenceArea x1={e.closed_from} x2={e.closed_to} fill="var(--warn)" fillOpacity={0.12} />
          <Tooltip {...TT} formatter={(v, k) => [usd(Number(v), 2), k === "back_forty" ? "Back Forty" : "Rest of floor"]} />
          <Legend formatter={(v) => (v === "back_forty" ? "Back Forty" : "Rest of floor")} wrapperStyle={{ fontSize: 12 }} />
          <Line isAnimationActive={false} dataKey="rest_of_floor" stroke="var(--chart-2)" dot={false} strokeWidth={1.25} />
          <Line isAnimationActive={false} dataKey="back_forty" stroke="var(--accent)" dot={false} strokeWidth={2} />
        </LineChart></ResponsiveContainer>
      </div>
      <p className="mt-2 text-[14px] leading-relaxed">While the walkway was closed, Back Forty (blue) fell well below the rest of the floor (grey): about <b>{Math.abs(n(e.estimate.observed_pct)).toFixed(0)}% less</b> than normal (estimate {n(e.estimate.observed_pct).toFixed(1)}%). When it reopened, Back Forty recovered.</p>
      <How steps={["The lines show expected casino win per machine-hour each day, using only machines that never moved.", "The shaded band is the closure. Compare the blue line’s distance from the grey line inside the band with outside it.", "Because both lines share the same days, casino-wide ups and downs (weekends, seasons) cancel out."]}
        technical={`${String(e.estimate.test)}; ${String(e.estimate.conclusion)}.`}
        formulas={[F.eventStudy(e.estimate.result_pct == null ? undefined : n(e.estimate.result_pct))]} />
    </Panel>
  );
}
