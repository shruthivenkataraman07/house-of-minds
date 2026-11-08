/**
 * Server-side bundle loader. Every file is checked against its manifest SHA-256 (and row
 * count for warehouse exports) before it reaches the UI; any mismatch throws so unverified
 * numbers are never rendered.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";

import type { Bundle } from "./types";

const ROOT = path.join(process.cwd(), "public", "data");

interface MEntry { dataset: string; file: string; sha256: string; rows?: number }
interface M { snapshot_id: string; exported_at_utc: string; files: MEntry[] }

function verified(dir: string): { manifest: M; get: (name: string) => unknown } {
  const manifest = JSON.parse(readFileSync(path.join(ROOT, dir, "manifest.json"), "utf8")) as M;
  return {
    manifest,
    get(name: string) {
      const e = manifest.files.find((f) => f.dataset === name);
      if (!e) throw new Error(`${dir}/${name} missing from manifest`);
      const text = readFileSync(path.join(ROOT, dir, e.file), "utf8");
      if (createHash("sha256").update(text).digest("hex") !== e.sha256) {
        throw new Error(`checksum mismatch: ${dir}/${name}`);
      }
      const data = JSON.parse(text);
      if (e.rows !== undefined && Array.isArray(data) && data.length !== e.rows) {
        throw new Error(`row count mismatch: ${dir}/${name}`);
      }
      return data;
    },
  };
}

export function loadBundle(): Bundle {
  const cur = verified("current");
  const side = verified("sidecar");
  if (side.manifest.snapshot_id !== cur.manifest.snapshot_id) {
    throw new Error("sidecar snapshot does not match the warehouse export snapshot");
  }
  const g = cur.get as (n: string) => never;
  const s = side.get as (n: string) => never;
  const machines = g("dash_machine_intelligence") as Bundle["machines"];
  const bankDay = s("bank_day") as { dates: string[]; banks: Bundle["banks"] };
  const contract = JSON.parse(readFileSync(path.join(ROOT, "current",
    "ask_the_house_contract.json"), "utf8")) as { entities: Record<string, string[]> };
  return {
    snapshotId: cur.manifest.snapshot_id,
    exportedAt: cur.manifest.exported_at_utc,
    sidecarSnapshotId: side.manifest.snapshot_id,
    verifiedFiles: cur.manifest.files.length + side.manifest.files.length,
    verdict: (g("ch_executive_verdict") as Bundle["verdict"][])[0],
    bottom10: (g("ch_machine_investigation") as Bundle["bottom10"]).sort(
      (a, b) => a.manager_rank - b.manager_rank),
    machines,
    candidates: g("ch_replacement_candidates"),
    councilReview: g("ch_council_manager_review"),
    portfolios: g("ch_portfolio_comparison"),
    passports: g("dash_decision_passports"),
    claims: g("dash_evidence_validation"),
    councilEvents: g("dash_council_activity"),
    whispers: g("council_whispers"),
    scenarios: g("dash_scenario_surface"),
    holdout: (g("dash_model_evaluation") as Bundle["holdout"]).sort(
      (a, b) => a.gaming_date.localeCompare(b.gaming_date)),
    forecast: g("forecast_baseline_comparison"),
    modelImpact: g("decision_model_impact"),
    kpis: g("dash_executive_kpis"),
    demandMonthly: g("ch_floor_demand_monthly"),
    demandWeekly: g("ch_floor_demand_weekly"),
    demandExplanations: g("ch_demand_explanations"),
    zoneDemand: g("ch_zone_demand"),
    zoneTraffic: g("ch_zone_traffic"),
    downtime: g("ch_downtime_economics"),
    downtimeByHour: g("ch_downtime_by_hour"),
    players: (g("ch_player_outcomes") as Bundle["players"][])[0],
    playersByTier: g("ch_player_outcomes_by_tier"),
    comps: g("ch_loyalty_comps"),
    floorDay: (s("floor_day") as { rows: Bundle["floorDay"] }).rows,
    bankDates: bankDay.dates,
    banks: bankDay.banks,
    machineBank: s("machine_bank"),
    robustness: s("audit_b4_robustness_matrix"),
    verification: s("audit_a3_a4_verification"),
    promoAudit: s("audit_c_promotion_portfolio"),
    auditInputs: s("audit_b_inputs"),
    metricDefs: g("aibi_metric_definitions"),
    measurementPlans: s("measurement_plans"),
    machineIds: contract.entities.machine ?? machines.map((m) => m.machine_id),
    zoneIds: contract.entities.zone ?? [],
  };
}
