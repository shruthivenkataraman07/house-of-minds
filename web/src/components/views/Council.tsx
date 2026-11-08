"use client";
import { useState } from "react";

import { useApi } from "@/lib/api";
import { allocation, signed, verdict } from "@/lib/format";
import type { CouncilDecision, CouncilSummary } from "@/lib/types";
import { useUI } from "@/lib/ui";

import { ErrorLine, EvidenceLink, Loading, PageHead, Panel, Pill, Scroll, Segmented, Tabs, verdictTone } from "../ui";

const KIND: Record<string, string> = { "review:luck": "Luck vs signal", "review:location": "Location & peers",
  "review:exposure": "Exposure", "review:hit_rate": "Payout frequency", "review:economics": "Lease economics" };
const KEY_EVENTS = new Set(["INDEPENDENT_FINDING", "GOSSIP_FINDING", "ASSUMPTION_REVISION_PROPOSED", "CHANGE_ADMITTED",
  "CLAIM_RETRACTED", "ESCALATION", "OPTIMIZER_EXECUTED", "COUNCIL_CONCLUDED"]);

export function Council() {
  const ui = useUI();
  const tab = ui.tab ?? "manager";
  const { data, error, reload } = useApi<CouncilSummary>("/council");
  return (
    <div className="space-y-4">
      <PageHead title="Council" line="Six rule-based agents; a deterministic verifier recomputes every claim." />
      <Tabs label="Decision under review" value={tab} onChange={(t) => ui.set({ tab: t })} tabs={[
        { id: "manager", label: "Replacement proposal" }, { id: "portfolio", label: "$100K hearing" }, { id: "agents", label: "Agents" }]} />
      {error && <ErrorLine error={error} retry={reload} />}
      {!data && !error && <Loading rows={6} />}
      {data && tab === "manager" && <ManagerReview s={data.data} />}
      {data && tab === "portfolio" && <Hearing />}
      {data && tab === "agents" && <Agents s={data.data} />}
    </div>
  );
}

function ManagerReview({ s }: { s: CouncilSummary }) {
  const ui = useUI();
  const [mid, setMid] = useState(ui.machineId && s.machines.some((m) => m.machine_id === ui.machineId) ? ui.machineId : s.machines[0].machine_id);
  const m = s.machines.find((x) => x.machine_id === mid)!;
  const claims = s.claims.filter((c) => c.machine === mid);
  const deciding = new Set((m.council_deciding_claims ?? "").split(",").filter(Boolean));
  const agree = s.machines.filter((x) => x.council_agrees).length;
  return (
    <div className="space-y-4">
      <ol className="panel grid gap-2 p-4 md:grid-cols-4" aria-label="Decision pathway">
        {[
          { h: "1 · Proposal", v: `Replace ${s.machines.length}`, sub: "manager, by lowest casino win", cls: "" },
          { h: "2 · Evidence challenges", v: `${s.claims.filter((c) => c.action === "CHALLENGE").length} challenges`, sub: `${s.claims.length} checks across luck, location, exposure, payout, economics`, cls: "" },
          { h: "3 · Objections verified", v: `${s.claims.filter((c) => c.verdict === "VERIFIED").length}/${s.claims.length}`, sub: "recomputed by the deterministic verifier", cls: "text-pos" },
          { h: "4 · Final disposition", v: `Replace ${s.machines.filter((x) => x.council_verdict === "REPLACE_JUSTIFIED_CONDITIONAL").length}`, sub: `matches analytics on ${agree}/10 (confirmation, not independent proof)`, cls: "text-neg" },
        ].map((st, i) => (
          <li key={st.h} className="relative rounded-md border border-line p-3">
            <p className="label">{st.h}</p>
            <p className={`num text-[18px] font-semibold ${st.cls}`}>{st.v}</p>
            <p className="label">{st.sub}</p>
            {i < 3 && <span aria-hidden className="absolute -right-2 top-1/2 z-10 hidden -translate-y-1/2 text-muted md:block">→</span>}
          </li>))}
      </ol>
      <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
        <Panel title="Machines" flush>
          <ul className="py-1">{s.machines.map((x) => (
            <li key={x.machine_id}><button type="button" aria-pressed={mid === x.machine_id} onClick={() => { setMid(x.machine_id); ui.set({ machineId: x.machine_id }); }}
              className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-[13px] ${mid === x.machine_id ? "bg-accent-soft" : "hover:bg-surface-2"}`}>
              <span><span className="label">{x.manager_rank}</span> {x.machine_id}</span><Pill tone={verdictTone(x.council_verdict)}>{verdict(x.council_verdict)}</Pill></button></li>))}</ul>
        </Panel>
        <Panel title={`${mid}: replace → ${verdict(m.council_verdict)}`} note={m.council_agrees ? "Council verdict matches the analytic verdict." : "Council verdict differs from the analytics."} flush
          right={<EvidenceLink id={mid}>Machine passport</EvidenceLink>}>
          <Scroll><table className="tbl min-w-[620px]"><thead><tr><th>Check</th><th>Agent</th><th>Finding</th><th className="text-right">Measured</th><th>Status</th><th>Impact</th></tr></thead>
            <tbody>{claims.map((c) => (
              <tr key={c.claim_id}>
                <td className="whitespace-nowrap text-[12.5px]">{KIND[c.kind] ?? c.kind}</td>
                <td className="whitespace-nowrap text-[12.5px] text-muted">{c.agent_name}</td>
                <td className="text-[12.5px]">{c.statement} <EvidenceLink id={c.claim_id} /></td>
                <td className="num whitespace-nowrap text-right text-[12.5px]">{c.numeric_result === null ? "—" : c.unit === "USD" ? signed(c.numeric_result) : `${c.numeric_result.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${c.unit}`}</td>
                <td><Pill tone={c.verdict === "VERIFIED" ? "pos" : "warn"}>{c.verdict.toLowerCase()}</Pill></td>
                <td>{deciding.has(c.claim_id) ? <Pill tone="accent">deciding</Pill> : <span className="label">{c.action.toLowerCase()}</span>}</td>
              </tr>))}</tbody></table></Scroll>
        </Panel>
      </div>
    </div>
  );
}

function Hearing() {
  const [cfg, setCfg] = useState("B_WHISPER_NETWORK");
  const { data, error, reload } = useApi<CouncilDecision>(`/council/${cfg}`);
  const ev = (data?.data.events ?? []).filter((e) => KEY_EVENTS.has(String(e.event_type)));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented label="Council configuration" value={cfg} onChange={setCfg} options={[{ id: "A_NO_GOSSIP", label: "Independent" }, { id: "B_WHISPER_NETWORK", label: "Whisper Network" }]} />
        {data && <Pill tone={data.data.portfolio_changed ? "warn" : "pos"}>{data.data.portfolio_changed ? "Adopted plan changed" : "Adopted plan confirmed"}</Pill>}
      </div>
      {error && <ErrorLine error={error} retry={reload} />}
      {!data && !error && <Loading rows={6} />}
      {data && (() => {
        const all = data.data.events;
        const cnt = (t: string) => all.filter((e) => e.event_type === t).length;
        const findings = cnt("INDEPENDENT_FINDING") + cnt("GOSSIP_FINDING");
        const admitted = all.filter((e) => e.event_type === "CHANGE_ADMITTED").map((e) => String(e.description));
        const opt = all.find((e) => e.event_type === "OPTIMIZER_EXECUTED" && String(e.description).startsWith("evidence_supported"));
        const before = opt ? String(opt.description).replace(/^evidence_supported:\s*/, "").split(" -> ")[0] : null;
        const revisions = all.filter((e) => e.event_type === "ASSUMPTION_REVISION_PROPOSED").map((e) => String(e.description).split(" -> ")[1]);
        const flip = data.data.scenario_flips.find((f) => f.startsWith("evidence_supported"));
        return (
          <div className="panel grid gap-4 p-4 md:grid-cols-3">
            <div><p className="label">Before council</p><p className="text-[15px] font-semibold">Optimizer plan</p><p className="label">{before ? allocation(before) : "not recorded"}</p></div>
            <div><p className="label">Challenge</p><p className="text-[15px] font-semibold">{findings} findings · {cnt("ASSUMPTION_REVISION_PROPOSED")} revisions · {cnt("CLAIM_RETRACTED")} retraction{cnt("CLAIM_RETRACTED") === 1 ? "" : "s"}</p><p className="label">{revisions.length ? `Promotion uplift tested at ${revisions.join(" and ")}` : "No assumption revisions"}</p></div>
            <div><p className="label">After council · final disposition</p><p className={`text-[15px] font-semibold ${data.data.portfolio_changed ? "text-warn" : "text-pos"}`}>{data.data.portfolio_changed ? "Plan changed" : "Plan confirmed"}</p><p className="label">{admitted.length ? `${admitted.length} revisions kept as scenarios${flip ? `; at the weakest value the plan would become ${allocation(flip.replace(/^evidence_supported:\s*/, "").split(" -> ")[1]?.split(" (")[0])}` : ""}` : "No revision admitted"}</p></div>
          </div>
        );
      })()}
      {data && (
        <Panel title="Review timeline" note={`${ev.length} key events of ${data.data.events.length} recorded; no generated dialogue.`} flush>
          <Scroll><table className="tbl min-w-[640px]"><thead><tr><th className="text-right">#</th><th>Actor</th><th>Event</th><th>Finding</th><th>Status</th></tr></thead>
            <tbody>{ev.map((e) => (
              <tr key={String(e.event_id)}>
                <td className="num text-right text-muted">{String(e.sequence)}</td>
                <td className="whitespace-nowrap text-[12.5px]">{String(e.actor).replace(/^AG\d_/, "").toLowerCase()}</td>
                <td className="whitespace-nowrap"><Pill tone={e.event_type === "CLAIM_RETRACTED" ? "neg" : e.event_type === "ESCALATION" ? "warn" : "muted"}>{String(e.event_type).replaceAll("_", " ").toLowerCase()}</Pill></td>
                <td className="text-[12.5px]">{String(e.description)} {e.claim_id && <EvidenceLink id={String(e.claim_id)} />}</td>
                <td className="text-[12px] text-muted">{e.verification_status ? String(e.verification_status).toLowerCase() : e.decision_consequence ? String(e.decision_consequence).toLowerCase() : "—"}</td>
              </tr>))}</tbody></table></Scroll>
        </Panel>
      )}
    </div>
  );
}

function Agents({ s }: { s: CouncilSummary }) {
  return (
    <Panel title="Agents" note="Rule-based programs, not language models." flush>
      <Scroll><table className="tbl min-w-[620px]"><thead><tr><th>Agent</th><th>Responsibility</th><th className="text-right">Proposal claims</th><th className="text-right">Verified</th><th className="text-right">Portfolio findings</th><th className="text-right">Retractions</th></tr></thead>
        <tbody>{s.agents.map((a) => (
          <tr key={a.agent_id}><td className="font-medium">{a.name}</td><td className="text-[12.5px] text-muted">{a.role}</td>
            <td className="num text-right">{a.manager_claims}</td><td className="num text-right">{a.manager_verified}</td>
            <td className="num text-right">{a.portfolio_findings}</td><td className={`num text-right ${a.retractions ? "text-neg" : ""}`}>{a.retractions}</td></tr>))}</tbody></table></Scroll>
    </Panel>
  );
}
