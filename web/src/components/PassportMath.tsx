"use client";
/** Typeset calculations for an evidence passport. Operands come from numeric API fields only. */
import { useApi } from "@/lib/api";
import { F } from "@/lib/formulas";
import type { MachineDetail, Passport } from "@/lib/types";
import { Formula, type FormulaSpec } from "./math";

const num = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);

function MachineMath({ id }: { id: string }) {
  const { data } = useApi<MachineDetail>(`/machines/${encodeURIComponent(id)}`);
  const d = data?.data;
  if (!d) return null;
  const g = d.diagnostics ?? {};
  const inv = d.investigation ?? {};
  const parts = ["gap_luck_usd", "gap_exposure_usd", "gap_location_usd", "gap_game_config_usd", "gap_machine_residual_usd"].map((k) => num(g[k]));
  const specs: FormulaSpec[] = [
    F.machineWin(num(inv.coin_in_usd), num(inv.payout_usd), num(g.house_win_usd), num(inv.rtp), num(g.theo_usd)),
    F.luckZ(num(g.house_win_usd), num(g.theo_usd), num(g.luck_residual_sd_usd), num(g.luck_z)),
    F.payingSpins(num(g.paying_spins), num(g.paid_spins), num(g.expected_hit_probability), num(g.hit_p_exact_bonferroni)),
    F.peerIndex(num(g.loo_peer_index), num(g.loo_peer_n)),
    F.decomposition(num(g.gap_vs_reference_usd), parts.every((p) => p !== undefined) ? (parts as number[]) : undefined),
    F.simulation(num(g.p_raw_bottom10_sim)),
  ];
  if (num(inv.lease_cost_usd) !== undefined) specs.push(F.leaseNet(num(inv.lease_net_planning_usd), num(inv.lease_net_best_case_usd), num(inv.lease_cost_usd)));
  return <>{specs.map((s) => <Formula key={s.title} spec={s} />)}</>;
}

/** Numbers quoted inside a recorded claim, matched by fixed patterns only (never evaluated as code). */
const money = (s: string | undefined) => (s === undefined ? undefined : Number(s.replace(/,/g, "")));

function ClaimMath({ p }: { p: Passport }) {
  const text = p.title;
  const flip = text.match(/^If A08_promo_excess_theo_per_day = ([\d,.]+) USD\/day, the evidence portfolio becomes HOLD \(was INV-PROMOx2; -([\d,.]+) USD modeled\)/);
  if (flip) return <Formula spec={F.decisionFlip(money(flip[1]), money(flip[2]))} />;
  const noise = text.match(/excess \(\$([\d,.]+)\/day\) is ([\d.]+) SD of ordinary Fri-Sun variation \(SD \$([\d,.]+)\/day\)/);
  if (noise) {
    const x = money(noise[1]), z = Number(noise[2]), s = money(noise[3]);
    // Show the substitution only if the recorded numbers reproduce the recorded ratio.
    const ok = x !== undefined && s !== undefined && Math.abs(x / s - z) < 0.01;
    return <Formula spec={F.noiseRatio(ok ? x : undefined, ok ? s : undefined, ok ? z : undefined)} />;
  }
  return <p className="rounded-md border border-dashed border-line px-3 py-2 text-[13px] text-muted">No formula is recorded for this claim. Its recorded result and the checks applied to it are listed below.</p>;
}

export function PassportMath({ p }: { p: Passport }) {
  const v = p.values ?? {};
  let body: React.ReactNode = null;
  if (p.kind === "machine") body = <MachineMath id={p.id} />;
  else if (p.kind === "claim") body = <ClaimMath p={p} />;
  else if (p.kind === "passport") {
    body = <>
      <Formula spec={F.actionNet(num(v.quantity), num(v.unit_cost), num(v.modeled_incremental_effect), num(v.modeled_net_contribution))} />
      {v.action_type_id === "A-PROMO" && <Formula spec={F.promotion()} />}
    </>;
  } else if (p.kind === "portfolio") {
    body = <Formula spec={F.portfolioNet(num(v.expected_incremental_contribution_usd), num(v.cost_usd), num(v.expected_net_benefit_usd), num(v.net_low_usd), num(v.net_high_usd))} />;
  }
  if (!body) return null;
  return (
    <section aria-label="How it is calculated" className="mb-4 space-y-3">
      <h3 className="text-[13px] font-semibold uppercase tracking-wide text-muted">How it is calculated</h3>
      {body}
    </section>
  );
}
