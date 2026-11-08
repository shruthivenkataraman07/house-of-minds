/**
 * Ask the House: deterministic intent router (no LLM, no generated SQL).
 *
 * Maps a question to one of the contract intents and validated entity ids. It never
 * produces numbers: answers are looked up from the snapshot record named in `answer`.
 * Unknown entity ids -> UNAVAILABLE; unidentified causal questions -> UNCERTAIN.
 */
export type Intent =
  | "select_entity"
  | "set_filters"
  | "get_evidence"
  | "compare_portfolios"
  | "open_council_challenge"
  | "explain_reversal"
  | "show_model_validation"
  | "navigate_dashboard";

export interface Contract {
  contract_version: string;
  snapshot_id: string;
  entities: Record<string, string[]>;
  synonyms: Record<string, string>;
  test_contracts: { question: string; intent: Intent; params: Record<string, unknown>;
    answer_record: string | null; expected: string }[];
}

export type RouteResult =
  | { status: "OK"; intent: Intent; params: Record<string, string | string[]>; answer: string }
  | { status: "UNAVAILABLE" | "UNCERTAIN" | "UNSUPPORTED"; reason: string; intent?: Intent };

const ID = {
  machine: /\bM-\d{4}\b/gi,
  claim: /\bCLM-[A-Z0-9-]+\b/gi,
  scenario: /\bS\d{2}[a-z]?_[a-z0-9_]+\b/gi,
};

const RULES: { intent: Intent; test: RegExp; answer: string }[] = [
  { intent: "show_model_validation", test: /\bgossip|whisper/i, answer: "CLM-WHISPER-EVAL" },
  { intent: "show_model_validation", test: /forecast|model|holdout|holt|baseline/i, answer: "CLM-FORECAST" },
  { intent: "explain_reversal", test: /invalid|withdraw/i, answer: "evidence_impact_results" },
  { intent: "explain_reversal", test: /5,?281|threshold|break.?even/i, answer: "CLM-PROMO-CAUSAL" },
  { intent: "explain_reversal", test: /regret/i, answer: "CLM-REGRET" },
  { intent: "explain_reversal", test: /change our|could change|revers|flip/i, answer: "decision_reversals" },
  { intent: "open_council_challenge", test: /statistician|challeng|council|agent/i, answer: "agent_claims" },
  { intent: "compare_portfolios", test: /conditional|compare|uncertain/i, answer: "CLM-PF-baseline-conditional" },
  { intent: "get_evidence", test: /support|evidence|why|promotion|underperform/i, answer: "claims_evidence_registry" },
];

const CAUSAL = /\b(definitely|guarantee|will .*increase|cause[sd]?|prove)\b/i;

export function route(question: string, contract: Contract): RouteResult {
  const q = question.trim();
  if (!q) return { status: "UNSUPPORTED", reason: "empty question" };
  const params: Record<string, string | string[]> = {};
  // entity ids: must exist in the contract, otherwise UNAVAILABLE (never guessed)
  for (const m of q.match(ID.machine) ?? []) {
    const idv = m.toUpperCase();
    if (!contract.entities.machine?.includes(idv)) {
      return { status: "UNAVAILABLE", reason: `unknown machine ${idv}`, intent: "select_entity" };
    }
    params.machine = idv;
  }
  for (const c of q.match(ID.claim) ?? []) {
    if (!contract.entities.claim?.includes(c)) {
      return { status: "UNAVAILABLE", reason: `unknown claim ${c}`, intent: "get_evidence" };
    }
    params.claim = c;
  }
  for (const [syn, target] of Object.entries(contract.synonyms)) {
    if (q.toLowerCase().includes(syn) && contract.entities.zone?.includes(target)) {
      params.zone = target;
    }
  }
  if (CAUSAL.test(q) && /promot/i.test(q)) {
    return { status: "UNCERTAIN", reason: "causal promotion effect not identified (CLM-PROMO-CAUSAL)",
      intent: "get_evidence" };
  }
  if (params.machine && /why|underperform|evidence/i.test(q)) {
    return { status: "OK", intent: "get_evidence", params, answer: `machine:${params.machine}` };
  }
  for (const r of RULES) {
    if (r.test.test(q)) return { status: "OK", intent: r.intent, params, answer: r.answer };
  }
  if (params.machine || params.zone) {
    return { status: "OK", intent: "select_entity", params, answer: "dash_machine_intelligence" };
  }
  return { status: "UNSUPPORTED", reason: "question not covered by the semantic contract" };
}
