/** Response types for /api/v1 (mirror backend/schemas/api.py). */
export type Rec = Record<string, string | number | boolean | null>;

export interface Meta {
  snapshot_id: string; data_mode: "snapshot" | "databricks";
  served_from: "snapshot" | "databricks" | "mixed"; exported_at_utc: string;
  official_window: string; decision_horizon: string; period: string | null; units: string;
  sources: string[];
}
export interface Envelope<T> { meta: Meta; data: T }

export interface Metadata {
  snapshot_id: string; exported_at_utc: string; verified_files: number; data_mode: string;
  live: boolean; note: string;
}

export interface Portfolio {
  option: string; allocation: string; action_types: number; cost_usd: number;
  remaining_budget_usd: number; expected_incremental_contribution_usd: number | null;
  expected_net_benefit_usd: number | null; net_low_usd: number | null; net_high_usd: number | null;
  uncertainty_basis: string; feasible: boolean; note: string; horizon: string; violations?: string;
}

export interface Executive {
  verdict: {
    answer: string; question: string; machines_reviewed: number; replacement_justified: number;
    retired_already: number; inspect_instead: number; not_economic: number;
    insufficient_evidence: number; council_agreement: number; recommended_option: string;
    recommended_allocation: string; recommended_cost_usd: number; recommended_net_usd: number;
    conditional_upside_cost_usd?: number; conditional_upside_net_usd?: number; limitations?: string;
  };
  bottom10: { machine_id: string; manager_rank: number; house_win_usd: number; verdict: string;
    council_verdict: string; lease_net_best_case_usd: number | null; machine_vs_peer_index: number;
    retire_date: string | null }[];
  portfolios: Portfolio[];
  kpis: Record<string, number>;
  promotion: { break_even: number; a08: { low: number; value: number; high: number };
    scenarios: Record<string, number> };
  council_claims: number; council_verified: number; floor_candidates: number;
  floor_planning_positive: number; floor_best_case_positive: number;
  inspection_cost_usd: number | null;
}

export interface MachineRow {
  machine_id: string; config_id: string; manufacturer: string; zone_id: string; zone_name: string;
  bank_id: string | null; house_win_usd: number; theo_usd: number;
  theo_per_available_hour_usd: number; available_hours: number; availability_rate: number;
  rank_raw: number; rank_luck_aware: number; rank_vs_peers: number; luck_z: number;
  hit_rate_z: number; payout_anomaly: boolean; manager_rank: number | null; verdict: string | null;
  lease_net_best_case_usd: number | null; robustness: string | null;
}
export interface MachinePage { total: number; offset: number; limit: number; rows: MachineRow[] }

export interface Claim {
  claim_id: string; agent_id: string; agent_name: string; machine: string; kind: string;
  statement: string; action: string; numeric_result: number | null; unit: string;
  query_refs: string; evidence_ids: string; verdict: string; arithmetic_valid: boolean;
}

export interface MachineDetail {
  machine: Rec; zone_name: string; bank_id: string | null; investigation: Rec | null;
  robustness: Rec | null; verification: Rec | null; candidate: Rec | null; council_claims: Claim[];
}

export interface Demand {
  period: { start: string; end: string }; exploratory: boolean;
  totals: { days: number; coin_in_usd: number; house_win_usd: number; theo_usd: number;
    hold: number | null; theo_hold: number | null; coin_in_per_day_usd: number | null;
    coin_in_per_available_hour_usd: number | null };
  weekly: { week_start: string; days: number; coin_in_per_day_usd: number;
    coin_in_per_available_hour_usd: number | null }[];
  zone_monthly: { zone_id: string; zone_name: string; month: string; theo_per_available_hour: number }[];
  explanations: Rec[];
}
export interface BankRow { bank_id: string; zone_id: string; zone_name: string; coin_in_usd: number;
  house_win_usd: number; theo_usd: number; available_hours: number; machine_days: number;
  hold: number | null; theo_per_available_hour_usd: number | null }
export interface BankList { period: { start: string; end: string }; exploratory: boolean; banks: BankRow[] }
export interface BankDetail { bank_id: string; totals: BankRow;
  daily: { gaming_date: string; coin_in_usd: number; house_win_usd: number; theo_usd: number }[];
  machines: string[] }
export interface Downtime { totals: Record<string, number>; by_manufacturer: Rec[]; by_hour: Rec[] }
export interface Players { summary: Rec; tiers: Rec[]; population: string }
export interface Comps { months: Rec[] }

export interface CouncilSummary {
  agents: { agent_id: string; name: string; role: string; manager_claims: number;
    manager_verified: number; portfolio_findings: number; retractions: number }[];
  decisions: { decision_id: string; label: string }[];
  machines: { machine_id: string; manager_rank: number; verdict: string; council_verdict: string;
    council_agrees: boolean; council_deciding_claims: string | null }[];
  claims: Claim[];
}
export interface CouncilDecision { decision_id: string; events: Rec[]; whispers: Rec[]; portfolio_changed: boolean }

export interface PromoScenario { scenario: string; A08: number; original_evidence: number;
  original_conditional: number; conditional_without_promo: number; evidence_without_promo: number }
export interface Promotion { a08: { low: number; value: number; high: number }; break_even_A08: number;
  minus_1506_meaning: string; scenarios: PromoScenario[];
  reoptimised_promo_prohibited: Record<string, { allocation: Record<string, number>; net: number }> }
export interface Portfolios { options: Portfolio[]; passports: Rec[]; measurement_plans: Rec[];
  promotion: Promotion; constraints: { check: string; pass: boolean; detail: string }[] }
export interface Scenarios { promotion: Promotion; stress: Rec[]; reversals: Rec[]; lease_operating_days: number | null }

export interface Passport { kind: string; id: string; title: string; fields: [string, string][]; links: string[] }
export interface EvidenceList { total: number; claims: Rec[]; classifications: Record<string, number>;
  passports: Rec[]; machines: string[]; verification: Rec[] }

export interface Forecast { comparison: Rec[]; holdout: Rec[]; decision_impact: Rec[]; protocol: Rec }

export interface AskAnswer {
  status: "OK" | "UNAVAILABLE" | "AMBIGUOUS" | "UNSUPPORTED" | "REFUSED"; intent: string;
  conclusion: string; support: string[]; period: string; evidence: string;
  uncertainty: string | null; premise_correction: string | null;
  action: { type: string; view: string; args: Record<string, string> } | null;
}
