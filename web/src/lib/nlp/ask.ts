/**
 * Ask the House: deterministic, schema-constrained intent router (no LLM, no SQL).
 *
 * question -> normalise -> safety screen -> entity extraction (validated against the
 * snapshot) -> ranked intent rules -> allowlisted action with validated args -> answer
 * composed only from bundle fields, with the period, evidence reference and uncertainty.
 */
import { OPTION_LABEL, label, pct, signedUsd, usd, zoneName } from "../metrics";
import type { Bundle } from "../types";

export const ACTIONS = ["select_entity", "set_filters", "compare_portfolios", "get_evidence",
  "explain_reversal", "open_validation", "open_council"] as const;
export type ActionType = (typeof ACTIONS)[number];

export interface Action {
  type: ActionType;
  view: "command" | "machines" | "operations" | "council" | "universes" | "decision" | "evidence"
    | "forecast";
  args: { machineId?: string; zoneId?: string; bankId?: string; tab?: string;
    evidence?: { kind: "claim" | "passport" | "machine" | "portfolio" | "audit"; id: string } };
}

export interface Answer {
  status: "OK" | "UNAVAILABLE" | "AMBIGUOUS" | "UNSUPPORTED" | "REFUSED";
  intent: string;
  conclusion: string;
  support: string[];
  period: string;
  evidence: string;
  uncertainty?: string;
  premiseCorrection?: string;
  action?: Action;
}

const OFFICIAL = "Official window Jan 1–Jun 30, 2025";
const HZ = "Decision horizon Jul 1–30, 2025 (modeled contribution, not realized profit)";

export function normalise(q: string): string {
  return q.toLowerCase().replace(/[’']/g, "'").replace(/\s+/g, " ").trim();
}

const SQL = /\b(select\s+.+\s+from|drop\s+table|insert\s+into|delete\s+from|update\s+\w+\s+set|union\s+select|;\s*--|truncate|alter\s+table)\b/i;
const WRITE = /\b(delete|drop|modify|change|update|overwrite|edit|set|write|insert|remove|alter)\b.*\b(data|table|record|row|value|number|verdict|database|dataset|machine|figure)s?\b/i;
const PII = /\b(player|guest)\s*(id|name|email|phone|address)\b|\bwho (is|are) the (biggest|heaviest)\b|\btarget\b.*\blos(ers|ing)\b/i;

const ZONE_SYN: Record<string, string> = {
  "back forty": "Z-B40", "b40": "Z-B40", "center pit": "Z-PIT", "centre pit": "Z-PIT",
  "main entrance": "Z-ENT", "entrance": "Z-ENT", "high limit": "Z-HL", "high-limit": "Z-HL",
  "bar row": "Z-BAR", "garage": "Z-GAR", "hotel": "Z-HTL",
};

export interface Ctx { machineId?: string | null; zoneId?: string | null }

export function ask(question: string, b: Bundle, ctx: Ctx = {}): Answer {
  const q = normalise(question);
  const base = { support: [] as string[], period: OFFICIAL, evidence: "" };
  if (!q) return { ...base, status: "UNSUPPORTED", intent: "none", conclusion: "Ask a question about the machines, the $100K plan, the council, demand, downtime, players, comps or the forecast." };
  if (SQL.test(q)) {
    return { ...base, status: "REFUSED", intent: "arbitrary_sql", conclusion: "Ask the House does not run SQL. It only answers from the verified snapshot through fixed, read-only actions.", evidence: "Allowlisted actions: " + ACTIONS.join(", ") };
  }
  if (WRITE.test(q) && !/\bwhat (if|happens)\b|\bscenario\b|\bwould\b/.test(q)) {
    return { ...base, status: "REFUSED", intent: "write", conclusion: "Ask the House is read-only: it cannot change data, verdicts or tables.", evidence: "No write actions exist in the allowlist." };
  }
  if (PII.test(q)) {
    return { ...base, status: "REFUSED", intent: "individual_player", conclusion: "Player data is shown only as tier and window aggregates. Individual guests are never identified or targeted.", evidence: "ch_player_outcomes_by_tier", action: { type: "set_filters", view: "operations", args: { tab: "players" } } };
  }

  // ---- entities (validated against the snapshot; never guessed)
  const ids = [...new Set((q.match(/\bm-?\d{4}\b/g) ?? []).map((m) => `M-${m.replace(/\D/g, "")}`))];
  for (const id of ids) {
    if (!b.machineIds.includes(id)) {
      return { ...base, status: "UNAVAILABLE", intent: "select_entity", conclusion: `Machine ${id} is not in the snapshot (310 machines, M-1001…). No figures are shown for an unknown ID.`, evidence: "dash_machine_intelligence" };
    }
  }
  const bankM = q.match(/\bbank\s*-?\s*([a-z0-9-]+)\b/);
  let bankId: string | undefined;
  if (bankM) {
    const cand = b.banks.find((x) => x.bank_id.toLowerCase().replace(/^b-?/, "") === bankM[1].replace(/^b-?/, ""));
    if (!cand) return { ...base, status: "UNAVAILABLE", intent: "select_entity", conclusion: `Bank "${bankM[1].toUpperCase()}" is not in the snapshot.`, evidence: "sidecar bank_day" };
    bankId = cand.bank_id;
  }
  let zoneId: string | undefined;
  for (const [k, z] of Object.entries(ZONE_SYN)) if (q.includes(k)) { zoneId = z; break; }
  const zm = q.match(/\bz-[a-z0-9]+\b/);
  if (zm) zoneId = b.zoneIds.find((z) => z.toLowerCase() === zm[0]) ?? zoneId;

  const refersBack = /\b(it|this machine|that machine|this one|that one)\b/.test(q);
  if (ids.length === 0 && refersBack && /machine|it\b/.test(q)) {
    if (ctx.machineId) ids.push(ctx.machineId);
    else return { ...base, status: "AMBIGUOUS", intent: "select_entity", conclusion: "Which machine? No machine is selected. Name one (for example M-5076) or pick it in Machine Intelligence.", evidence: "" };
  }
  if (ids.length > 1 && !/compare|vs|versus/.test(q)) {
    return { ...base, status: "AMBIGUOUS", intent: "select_entity", conclusion: `Several machines were named (${ids.join(", ")}). Ask about one at a time.`, evidence: "" };
  }

  const v = b.verdict;
  const mgr = b.portfolios.find((p) => p.option === "manager_proposal_lease");
  const hom = b.portfolios.find((p) => p.option === v.recommended_option);
  const pa = b.promoAudit;
  const allMatch = /\b(all|every)\b/.test(q);
  const pb = b.robustness.map((r) => r["payback_days_after_install_at_A10_0.5"]);
  const ss = b.robustness.map((r) => r.steady_state_breakeven_A10);
  const payback = `${Math.round(Math.min(...pb))}–${Math.round(Math.max(...pb))} days`;
  const ssRange = `${Math.round(Math.min(...ss) * 100)}–${Math.round(Math.max(...ss) * 100)}%`;
  const c0 = b.comps[0], cN = b.comps[b.comps.length - 1];

  // ---- ranked intents
  if (/forecast|holdout|holt|model|predict|baseline|mlflow|validation|reliab/.test(q) && !ids.length) {
    const all = b.forecast.find((f) => f.subset === "all");
    const ev = b.forecast.find((f) => f.subset === "event_days");
    return { status: "OK", intent: "open_validation", period: "Train Jan–Mar, validate Apr, holdout May 1–Jun 30, 2025 (61 days)",
      conclusion: `Holt-Winters beat the weekday-mean baseline on the chronological holdout overall (MAE ${usd(all?.candidate_mae)} vs ${usd(all?.baseline_mae)}/day, ${all?.mae_improvement_pct.toFixed(1)}% better), but it was worse on promotion/event days (${ev?.mae_improvement_pct.toFixed(1)}%).`,
      support: [`80% interval coverage ${pct(all?.candidate_coverage80)} overall, ${pct(ev?.candidate_coverage80)} on event days: intervals are too narrow.`, "Stored in Delta tables; no MLflow model exists."],
      evidence: "forecast_baseline_comparison · dash_model_evaluation",
      uncertainty: "The one decision the model changes (keeping promotions in the weakest-event case) depends on event-day accuracy, where it underperforms; the audit rates that effect INSUFFICIENT EVIDENCE.",
      action: { type: "open_validation", view: "forecast", args: {} } };
  }

  if (ids.length === 1) {
    const id = ids[0];
    const inv = b.bottom10.find((m) => m.machine_id === id);
    const row = b.machines.find((m) => m.machine_id === id)!;
    const rob = b.robustness.find((r) => r.machine_id === id);
    const cand = b.candidates.find((c) => c.machine_id === id);
    const support: string[] = [`House win ${usd(row.house_win_usd)} vs theo ${usd(row.theo_usd)} (luck z ${row.luck_z.toFixed(2)}); ${zoneName(row.zone_id)}, ${row.config_id}.`,
      `Theo per available hour ${usd(row.theo_per_available_hour, 2)}; raw rank ${row.rank_raw}, luck-aware ${row.rank_luck_aware}, vs same-game peers ${row.rank_vs_peers} (of 310).`];
    let conclusion: string;
    if (inv) {
      conclusion = `${id} is #${inv.manager_rank} on the manager's list. Verdict: ${label(inv.verdict)}. ${inv.recommended_alternative}.`;
      if (inv.lease_net_planning_usd !== null) support.push(`Lease replacement net over 16 operating days: ${signedUsd(inv.lease_net_planning_usd)} at the planning value, ${signedUsd(inv.lease_net_best_case_usd)} at the zone's best observed title.`);
      if (inv.retire_date) support.push(`Retired ${inv.retire_date.slice(0, 10)}.`);
      if (inv.verdict === "DO_NOT_REPLACE_INSPECT") support.push(`Hit-rate z = ${inv.hit_rate_z.toFixed(1)} vs game math (Bonferroni p < 0.001).`);
      support.push(`Council: ${label(inv.council_verdict)} (${inv.council_agrees ? "agrees" : "disagrees"}).`);
    } else {
      conclusion = `${id} is not on the manager's bottom-10 list.` + (cand ? ` As a replacement candidate it nets ${signedUsd(cand.lease_net_planning_usd)} at the planning value and ${signedUsd(cand.lease_net_best_case_usd)} in the best case.` : " It is not a replacement candidate (no positive best case).");
    }
    const unc = rob ? `Robustness: ${rob.robustness}. Conservative ${signedUsd(rob["conservative_A10_0.25_cann_0.25"])}, base ${signedUsd(rob["base_A10_0.5"])}, optimistic ${signedUsd(rob["optimistic_A10_1.0"])}; July break-even needs ${(rob.breakeven_A10_july * 100).toFixed(0)}% gap capture.` : undefined;
    return { status: "OK", intent: "select_entity", conclusion, support, period: `${OFFICIAL}; economics ${HZ}`,
      evidence: inv ? `ch_machine_investigation · council claims ${inv.council_deciding_claims ?? ""}` : "dash_machine_intelligence",
      uncertainty: unc, action: { type: "select_entity", view: "machines", args: { machineId: id } } };
  }

  if (/zero|no (promo|uplift)|without (the )?promo|promo.*(fail|nothing|zero)|uplift.*(zero|0\b)/.test(q)) {
    const z = pa.scenarios.find((s) => s.scenario === "zero_uplift")!;
    const w = pa.scenarios.find((s) => s.scenario === "weakest_event")!;
    return { status: "OK", intent: "explain_reversal", period: HZ,
      conclusion: `If promotion uplift is zero, the two weekends lose their full cost: the evidence-supported plan nets ${signedUsd(z.original_evidence)}. With promotions removed, the best remaining plan is ${signedUsd(z.conditional_without_promo)} (inspect M-1158 + 2 moves) or hold.`,
      support: [`Break-even uplift: ${usd(pa.break_even_A08)}/day excess theo. The weakest observed event was ${usd(pa.a08.low)}/day, giving ${signedUsd(w.original_evidence)}.`, `Base case (mean of 2 events): ${signedUsd(pa.scenarios.find((s) => s.scenario === "base_mean")?.original_evidence)}.`],
      evidence: "audit c_promotion_portfolio · decision_model_impact",
      uncertainty: "Uplift rests on 2 historical events with no control group; it is associational, not causal.",
      action: { type: "explain_reversal", view: "decision", args: { tab: "promotion" } } };
  }

  if (/council|agent|challeng|object|statistician|cfo|whisper|debate/.test(q)) {
    const changed = b.bottom10.filter((m) => m.council_verdict !== m.verdict).length;
    const premise = /reject|overturn|veto|block|disagree/.test(q) && /promo|portfolio|plan|recommend/.test(q)
      ? "Premise check: the council did not reject the recommended promotion plan. It flagged its dependence on uplift (A08) as a fragility and kept it." : undefined;
    return { status: "OK", intent: "open_council", period: OFFICIAL,
      conclusion: `The council reviewed the manager's proposal with ${b.councilReview.length} claims (${b.councilReview.filter((c) => c.verdict === "VERIFIED").length} verified by the deterministic verifier) and reached the analytic verdict on ${10 - changed}/10 machines, overturning "replace" for all 10.`,
      support: ["The council challenged luck (Statistician), location (Demand), exposure and payout faults (Operations), and lease economics (CFO).", "In the portfolio review it retracted one causal claim and flagged the promotion uplift as the key fragility. It did not change the recommended portfolio."],
      evidence: "ch_council_manager_review · dash_council_activity · council_whispers",
      uncertainty: "Agents are rule-based and use the same rules as the analytics, so 10/10 agreement is a reproducibility check, not independent confirmation.",
      premiseCorrection: premise, action: { type: "open_council", view: "council", args: {} } };
  }

  if (/compare|manager'?s plan|versus|vs\.?|alternative|which plan|better plan|portfolio/.test(q)) {
    return { status: "OK", intent: "compare_portfolios", period: HZ,
      conclusion: `Manager's plan (lease ${b.bottom10.filter((m) => m.verdict !== "RETIRED_ALREADY").length} on-floor machines): ${usd(mgr?.cost_usd)} for ${signedUsd(mgr?.expected_net_benefit_usd)} modeled net. House of Minds: ${usd(hom?.cost_usd)} for ${signedUsd(hom?.expected_net_benefit_usd)}.`,
      support: [`Manager range ${signedUsd(mgr?.net_low_usd)} to ${signedUsd(mgr?.net_high_usd)} (${mgr?.uncertainty_basis}).`, `House of Minds range ${signedUsd(hom?.net_low_usd)} to ${signedUsd(hom?.net_high_usd)} (${hom?.uncertainty_basis}).`, "Buying 10 machines ($220,000) breaks the $100,000 budget."],
      evidence: "ch_portfolio_comparison",
      uncertainty: "The recommended plan is positive at the base case but negative at the weakest observed promotion; it is conditional on uplift.",
      action: { type: "compare_portfolios", view: "universes", args: {} } };
  }

  if (/break.?even|revers|flip|threshold|what would change|sensitiv|robust/.test(q)) {
    return { status: "OK", intent: "explain_reversal", period: HZ,
      conclusion: `The recommendation flips to HOLD if promotion excess theo falls below ${usd(pa.break_even_A08)}/day; the weakest observed event (${usd(pa.a08.low)}/day) is just below it.`,
      support: [`"Replace none" holds within July under every tested variant; the not-economic vs insufficient-evidence split is conditional on lease structure and the ceiling.`, `After July, replacements at the planning value would pay back in ${payback}: the July-only verdict is horizon-specific.`],
      evidence: "audit b4_robustness_matrix · c_promotion_portfolio · dash_scenario_surface",
      action: { type: "explain_reversal", view: "universes", args: { tab: "reversals" } } };
  }

  if (/downtime|outage|broke|fault|repair|availability|maintenance/.test(q)) {
    const total = b.downtime.reduce((s, r) => s + Number(r.downtime_hours), 0);
    const risk = b.downtime.reduce((s, r) => s + Number(r.theo_at_risk_usd), 0);
    const top = [...b.downtimeByHour].sort((a, c) => Number(c.downtime_hours) - Number(a.downtime_hours))[0];
    return { status: "OK", intent: "set_filters", period: OFFICIAL,
      conclusion: `${Math.round(total).toLocaleString()} machine-hours of downtime put ${usd(risk)} of theoretical win at risk (opportunity, not guaranteed loss).`,
      support: [`Worst hour of day: ${String(top.local_hour).padStart(2, "0")}:00 (${Math.round(Number(top.downtime_hours))} h).`, `Manager-list machines with the most downtime: ${[...b.bottom10].sort((a, c) => c.downtime_hours - a.downtime_hours).slice(0, 3).map((m) => `${m.machine_id} ${Math.round(m.downtime_hours)} h`).join(", ")}.`],
      evidence: "ch_downtime_economics · ch_downtime_by_hour", uncertainty: "Theo at risk assumes lost play would not move to other machines.",
      action: { type: "set_filters", view: "operations", args: { tab: "downtime", zoneId } } };
  }

  if (/demand|traffic|coin.?in|zone|busy|visits|walkway/.test(q) || zoneId || bankId) {
    const ex = b.demandExplanations[0];
    return { status: "OK", intent: "set_filters", period: OFFICIAL,
      conclusion: `${String(ex.change)}: ${Number(ex.observed_pct).toFixed(1)}%. Per available machine-hour: ${Number(ex.result_pct).toFixed(1)}%, so fewer machines do not explain it.`,
      support: [String(ex.conclusion), zoneId ? `Filtered to ${zoneName(zoneId)}.` : b.demandExplanations[1] ? `${b.demandExplanations[1].change}: ${Number(b.demandExplanations[1].observed_pct).toFixed(1)}% (${b.demandExplanations[1].conclusion}).` : ""],
      evidence: "ch_floor_demand_monthly · ch_zone_demand · ch_demand_explanations",
      uncertainty: "Traffic counters count crossings; offline hours are missing, not zero.",
      action: { type: "set_filters", view: "operations", args: { tab: "demand", zoneId, bankId } } };
  }

  if (/loyal|tier|guest|player|tracked|comp|points|segment/.test(q)) {
    const p = b.players;
    const comps = /comp|points/.test(q);
    return { status: "OK", intent: "set_filters", period: OFFICIAL,
      conclusion: comps ? `Points per comp dollar went from ${Number(c0.points_per_comp_usd).toFixed(1)} (${c0.month}) to ${Number(cN.points_per_comp_usd).toFixed(1)} (${cN.month}); comp cost per carded theo from ${pct(Number(c0.comp_cost_per_carded_theo), 2)} to ${pct(Number(cN.comp_cost_per_carded_theo), 2)}. The change took effect May 1, 2025.`
        : `Tracked (carded) players wagered ${usd(Number(p.tracked_coin_in_usd))} and lost ${usd(-Number(p.tracked_player_net_usd))} net; ${pct(Number(p.share_players_ahead))} finished ahead. The top 10% account for ${pct(Number(p.top10pct_share_of_theo))} of tracked theo.`,
      support: b.playersByTier.map((t) => `${t.tier}: ${Number(t.players).toLocaleString()} players, ${usd(Number(t.theo))} theo`),
      evidence: comps ? "ch_loyalty_comps" : "ch_player_outcomes · ch_player_outcomes_by_tier",
      uncertainty: `Carded play only (${pct(Number(p.carded_share_of_all_coin_in))} of coin-in); not comparable with all-play meter totals.`,
      action: { type: "set_filters", view: "operations", args: { tab: comps ? "comps" : "players" } } };
  }

  if (/evidence|source|prove|trace|passport|how do (we|you) know|support/.test(q)) {
    const pp = b.passports.find((x) => x.portfolio_mode === "evidence_supported");
    return { status: "OK", intent: "get_evidence", period: HZ,
      conclusion: `The recommendation (${v.recommended_allocation}) is documented in passport ${pp?.passport_id}: cost, modeled effect, assumptions, council claims, reversal conditions and its measurement plan.`,
      support: [`Effect classification: ${pp?.effect_classification}.`, `${b.claims.length} registered claims; ${b.claims.filter((c) => c.verification_status === "PASS").length} pass verification.`],
      evidence: pp?.passport_id ?? "dash_decision_passports",
      action: { type: "get_evidence", view: "evidence", args: { evidence: { kind: "passport", id: pp?.passport_id ?? "" } } } };
  }

  if (/replace|bottom|lowest|worst|10 machines|ten machines|manager/.test(q) || allMatch) {
    const premise = /why (should|do) (we|i) replace|replace all/.test(q) ? "Premise check: the evidence does not support replacing these machines." : undefined;
    return { status: "OK", intent: "get_evidence", period: `${OFFICIAL}; economics ${HZ}`,
      conclusion: `${label(v.answer)}. Of the 10 lowest earners: ${v.retired_already} already retired, ${v.inspect_instead} needs inspection instead (payout fault), ${v.not_economic} lose money on a lease even with the best title seen in their zone, and ${v.insufficient_evidence} has insufficient evidence.`,
      support: [`Manager's lease plan: ${signedUsd(mgr?.expected_net_benefit_usd)} for ${usd(mgr?.cost_usd)}.`, `${b.bottom10.filter((m) => m.zone_id === "Z-B40").length}/10 sit in Back Forty; median same-game peer index ${[...b.bottom10].map((m) => m.machine_vs_peer_index).sort((a, c) => a - c)[5].toFixed(2)}; M-5076 was on the floor ${b.bottom10.find((m) => m.machine_id === "M-5076")?.active_days ?? "n/a"} days.`, `Council agreement ${v.council_agreement}/10.`],
      evidence: "ch_executive_verdict · ch_machine_investigation",
      uncertainty: `Within July only. Over a longer horizon replacements could pay back (${payback}) if a new title captures at least ${ssRange} of the gap to the zone's best title, which is unmeasured.`,
      premiseCorrection: premise,
      action: { type: "select_entity", view: "machines", args: {} } };
  }

  if (/spend|100k|\$?100,?000|budget|invest|recommend|what should/.test(q)) {
    return { status: "OK", intent: "compare_portfolios", period: HZ,
      conclusion: `Spend ${usd(v.recommended_cost_usd)} on ${v.recommended_allocation.replace("INV-PROMOx2", "two promotion weekends")} (modeled net ${signedUsd(v.recommended_net_usd)}) and keep ${usd(100000 - v.recommended_cost_usd)} in reserve.`,
      support: [`Conditional upside: ${usd(v.conditional_upside_cost_usd)} for ${signedUsd(v.conditional_upside_net_usd)} (${v.conditional_basis}).`, `${OPTION_LABEL[mgr?.option ?? ""]}: ${signedUsd(mgr?.expected_net_benefit_usd)}.`],
      evidence: "ch_portfolio_comparison · dash_decision_passports",
      uncertainty: "Promotion uplift is associational (2 events, no control).",
      action: { type: "compare_portfolios", view: "decision", args: {} } };
  }

  return { ...base, status: "UNSUPPORTED", intent: "none",
    conclusion: "That question is outside what the verified snapshot can answer.",
    support: ["Try: “Why shouldn't we replace the bottom 10?”, “Explain M-5076”, “Compare the manager's plan with House of Minds”, “What if promotion uplift is zero?”, “How reliable is the forecast?”"],
    evidence: "" };
}
