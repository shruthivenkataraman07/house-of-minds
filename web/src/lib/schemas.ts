/**
 * Runtime data contracts for the House of Minds public snapshot (Step 6 serving datasets).
 * Databricks is the analytical authority: these schemas validate, they never recompute.
 * Unknown extra columns are allowed (passthrough) so the snapshot can grow safely.
 */
import { z } from "zod";

const usd = z.number().finite();
const id = z.string().min(1);
const nullableNum = z.number().finite().nullable();

export const SnapshotId = z.string().regex(/^chf-v1:[0-9a-f]{16}$/);

export const ManifestFile = z.object({
  dataset: id,
  file: id,
  rows: z.number().int().nonnegative(),
  warehouse_rows: z.number().int().nonnegative(),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
  columns: z.array(z.string()),
});
export const Manifest = z
  .object({
    snapshot_id: SnapshotId,
    source: z.string(),
    exported_at_utc: z.string(),
    files: z.array(ManifestFile).min(1),
    semantic_contract: z.string(),
  })
  .refine((m) => m.files.every((f) => f.rows === f.warehouse_rows), {
    message: "exported rows must equal warehouse rows",
  });

export const ExecutiveKpi = z.looseObject({
  kpi: id,
  value: z.number().finite(),
  unit: z.string(),
  formula: z.string(),
  claim_id: id,
  period: z.string(),
  snapshot_id: SnapshotId,
});

export const MachineRow = z.looseObject({
  machine_id: z.string().regex(/^M-\d{4}$/),
  zone_id: z.string().nullable(),
  manufacturer: z.string(),
  house_win_usd: usd,
  theo_usd: usd,
  coin_in_usd: usd,
  luck_z: z.number(),
  available_hours: z.number().nonnegative(),
  theo_per_available_hour: z.number(),
  rank_raw: z.number().int(),
  rank_luck_aware: z.number().int(),
  explanation: z.string(),
  snapshot_id: SnapshotId,
});

export const PortfolioLine = z
  .looseObject({
    line_id: id,
    portfolio_id: id,
    mode: z.enum(["evidence_supported", "conditional"]),
    role: z.string(),
    investment_id: id,
    quantity: z.number().int().positive(),
    unit_cost: usd,
    line_cost: usd,
    line_net: usd,
    total_cost: usd.max(100_000),
    net_benefit: usd,
    snapshot_id: SnapshotId,
  })
  .refine((r) => Math.abs(r.line_cost - r.unit_cost * r.quantity) < 0.01, {
    message: "line_cost must equal unit_cost x quantity",
  });

export const ScenarioRow = z.looseObject({
  scenario_id: id,
  row_type: z.enum(["scenario", "reversal"]),
  regret: nullableNum.optional(),
  snapshot_id: SnapshotId,
});

export const CouncilEvent = z.looseObject({
  event_id: id,
  config: z.enum(["A_NO_GOSSIP", "B_WHISPER_NETWORK"]),
  sequence: z.number().int().positive(),
  event_type: id,
  actor: id,
  description: z.string(),
});

export const EvidenceClass = z.enum([
  "VERIFIED_OBSERVATION",
  "VERIFIED_ARITHMETIC",
  "STATISTICAL_ESTIMATE",
  "MODELED_SCENARIO",
  "PLANNING_ASSUMPTION",
  "CAUSAL_EFFECT_NOT_IDENTIFIED",
  "RETRACTED",
  "INVALIDATED",
  "UNRESOLVED",
]);

export const ClaimRow = z.looseObject({
  claim_id: id,
  category: id,
  claim_text: z.string(),
  source_table: z.string().min(1),
  query_ref: z.string().min(1),
  result: z.string(),
  alternative_explanation: z.string().min(1),
  limitation: z.string().min(1),
  evidence_classification: EvidenceClass,
  verification_status: z.string(),
  snapshot_id: SnapshotId,
});

export const HoldoutDay = z.looseObject({
  gaming_date: z.string(),
  actual: usd,
  baseline_pred: usd,
  candidate_pred: usd,
  candidate_lo80: usd,
  candidate_hi80: usd,
  is_event_day: z.boolean(),
  evaluation_run_id: id,
});

export const Passport = z
  .looseObject({
    passport_id: id,
    passport_schema_version: z.literal("passport-v1"),
    portfolio_id: id,
    portfolio_mode: z.enum(["evidence_supported", "conditional"]),
    action_type_id: z.string().regex(/^A-[A-Z-]+$/),
    quantity: z.number().int().positive(),
    unit_cost: usd,
    total_cost: usd,
    portfolio_total_cost: usd.max(100_000),
    remaining_budget: usd.min(0),
    modeled_net_contribution: usd,
    effect_classification: z.string(),
    measurement_plan_id: z.string().nullable(),
    snapshot_id: SnapshotId,
  })
  .refine((p) => Math.abs(p.portfolio_total_cost + p.remaining_budget - 100_000) < 0.01, {
    message: "portfolio cost + remaining budget must equal $100,000",
  });

export const Whisper = z.looseObject({
  message_id: id,
  config: z.string(),
  sender_agent_id: id,
  recipient_agent_id: id,
  message_type: z.enum(["WHISPER", "REQUEST_CHECK", "COUNTERCLAIM", "ESCALATE", "RETRACT", "ACKNOWLEDGE"]),
  message_status: z.string(),
  flagged_retracted_origin: z.boolean(),
});

export const DATASET_SCHEMAS = {
  dash_executive_kpis: ExecutiveKpi,
  dash_machine_intelligence: MachineRow,
  dash_investment_portfolios: PortfolioLine,
  dash_scenario_surface: ScenarioRow,
  dash_council_activity: CouncilEvent,
  dash_evidence_validation: ClaimRow,
  dash_model_evaluation: HoldoutDay,
  dash_decision_passports: Passport,
  council_whispers: Whisper,
} as const;

export type DatasetName = keyof typeof DATASET_SCHEMAS;
export type Row<N extends DatasetName> = z.infer<(typeof DATASET_SCHEMAS)[N]>;
