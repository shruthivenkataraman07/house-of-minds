"""Evidence Vault: invalidation impact, accountability, AI audit, reproducibility,
serving datasets and the Ask-the-House semantic contract (all from persisted records)."""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from vault.build import jl, sid
from vault.graph import Graph

SECRET = re.compile(r"(dapi[0-9a-f]{16,}|Bearer\s+[A-Za-z0-9._-]{20,}|sk-[A-Za-z0-9]{20,}|"
                    r"client_secret|refresh_token)", re.I)
PERSONAL_COLUMNS = re.compile(r"(player_id|observed_visit_id|transaction_id|home_region|"
                              r"age_band|enrolled)", re.I)


# --------------------------------------------------------------------------- invalidation
def invalidation_impacts(g: Graph, model: Any, snapshot: str) -> list[dict[str, Any]]:
    from optimization.decision_analysis import invalidation_test
    from optimization.portfolio import MODE_CONDITIONAL, MODE_EVIDENCE
    cases = [("INV-PROMO-EVIDENCE", "ASM:A08_promo_excess_theo_per_day",
              "A08_promo_excess_theo_per_day"),
             ("INV-PAYOUT-EVIDENCE", "EV:EV-1C684B792E7B", "A02_m1158_loss_per_day")]
    rows: list[dict[str, Any]] = []
    for case, node, asm in cases:
        imp = g.impact(node)
        portfolios = {n for n in imp["direct"] if n.startswith("PF:")}
        event = sid("IVE", snapshot, case)
        for cls in ("direct", "possible"):
            for n in sorted(imp[cls]):
                rows.append({"invalidation_event_id": event, "case": case,
                             "invalidated_node": node, "affected_node": n,
                             "affected_type": g.nodes[n].node_type, "impact_class": cls,
                             "meaning": "support removed: must be revalidated" if cls ==
                             "direct" else "argument/display may change: review",
                             "snapshot_id": snapshot})
        for mode in (MODE_EVIDENCE, MODE_CONDITIONAL):
            r = invalidation_test(model, asm, mode)
            rows.append({"invalidation_event_id": event, "case": case,
                         "invalidated_node": node, "affected_node": f"OPTIMIZER:{mode}",
                         "affected_type": "optimizer_recompute",
                         "impact_class": "decision_changed" if r["decision_changed"]
                         else "decision_unchanged",
                         "meaning": f"{r['before']} -> {r['after']} (Step 3 invalidation "
                                    f"pathway, status {r['status']})",
                         "snapshot_id": snapshot,
                         "graph_predicted_affected": any(
                             mode.split("_")[0] in g.nodes[p].label for p in portfolios)})
    return rows


# --------------------------------------------------------------------------- accountability
def measurement_register(T: dict[str, pd.DataFrame], snapshot: str) -> list[dict[str, Any]]:
    cat = T["action_catalog"].set_index("action_type_id")
    out = []
    for p in T["action_measurement_plans"].itertuples():
        lead = int(cat.loc[p.action_id, "lead_days"])
        start = pd.Timestamp("2025-07-01") + pd.Timedelta(days=lead)
        out.append({
            "measurement_plan_id": f"MP-{p.action_id}", "action_id": p.action_id,
            "investment": p.investment, "cost": float(p.total_cost),
            "expected_effect": p.expected_effect,
            "effect_classification": p.evidence_classification,
            "baseline_kpi": p.baseline_kpi, "outcome_metric": p.baseline_kpi,
            "exposure_adjustment": "per available machine-hour (theo / available hours)",
            "implementation_date": str(start.date()),
            "measurement_window": p.observation_period,
            "comparison_strategy": p.comparison_method, "confounders": p.confounders,
            "success_threshold": p.success_threshold, "failure_threshold": p.stop_or_revise,
            "review_owner": "not defined in project records",
            "decision_rule": p.stop_or_revise,
            "uncertainty_reduced": p.uncertainty,
            "measurement_status": "PLANNED_NOT_STARTED (no implementation results exist)",
            "snapshot_id": snapshot})
    return out


def ai_usage_audit(T: dict[str, pd.DataFrame], snapshot: str) -> list[dict[str, Any]]:
    runs = T["council_runs"]
    tokens = int(pd.to_numeric(runs.llm_tokens).sum())
    cost = float(pd.to_numeric(runs.llm_cost_usd).sum())
    me = T["model_evaluation_runs"].iloc[0]
    rows: list[dict[str, Any]] = [
        {"area": "A. Coding assistance", "implementation": "Claude Code (Anthropic) in VS "
         "Code wrote and ran the code, SQL, tests and docs under human direction",
         "evidence": "docs/AI_USE_LOG.md entries per step", "llm_used": True,
         "status": "USED (development only; not part of the analytical pipeline)"},
        {"area": "B. Predictive modeling", "implementation": f"{me.candidate_method}; "
         f"baseline {me.baseline_method}; holdout {me.holdout}",
         "evidence": f"model_evaluation_runs {me.evaluation_run_id}", "llm_used": False,
         "status": "statsmodels time-series model, not an LLM"},
        {"area": "C. Adversarial council", "implementation": "Six RULE_BASED specialist "
         "agents: deterministic analyses over allowlisted read-only tools",
         "evidence": f"council_runs.execution_mode = {sorted(set(runs.execution_mode))}",
         "llm_used": False, "status": "NOT LLM agents"},
        {"area": "D. Whisper Network", "implementation": "Deterministic routing, budgets, "
         "origin tracking, duplicate suppression, retraction propagation",
         "evidence": "council_whispers", "llm_used": False, "status": "deterministic"},
        {"area": "E. LLM calls in the product", "implementation": "None; an adapter exists "
         "(council/llm.py) but is not called and no provider is configured",
         "evidence": f"llm_tokens={tokens}, llm_cost_usd={cost}", "llm_used": False,
         "status": "NONE"},
        {"area": "F. Natural-language interface", "implementation": "Ask the House "
         "semantic contract only; no chat interface exists",
         "evidence": "semantic/ask_the_house_contract.json", "llm_used": False,
         "status": "NOT YET IMPLEMENTED"},
        {"area": "G. Human oversight", "implementation": "Causal promotion uplift, "
         "inspection fix probability, move transfer, cross-platform forecast metrics",
         "evidence": "claims_evidence_registry", "llm_used": False,
         "status": "requires human / experimental validation"},
    ]
    return [{**r, "snapshot_id": snapshot} for r in rows]


def reproducibility_manifest(T: dict[str, pd.DataFrame], snapshot: str,
                             counts: dict[str, int], jobs: dict[str, Any]
                             ) -> list[dict[str, Any]]:
    me = T["model_evaluation_runs"].iloc[0]
    rows = [
        {"item": "repository_commit", "value": "NONE (no commits authorised)",
         "note": "content hashes used instead"},
        {"item": "dataset", "value": f"Dashboard Royale "
         f"{jl(T['evidence_ledger'].dataset_fingerprint.iloc[0])} (manifest fingerprint)",
         "note": "31 official tables, SHA-256 verified (Step 1/2)"},
        {"item": "canonical_snapshot", "value": snapshot,
         "note": "chf-v1 contract; matches local and Databricks"},
        {"item": "historical_fingerprints", "value": "991446d9be867b7c (local), "
         "de50d70f0b78336b (Databricks)", "note": "preserved, not rewritten"},
        {"item": "step5_protocol_sha256", "value": me.protocol_sha256,
         "note": "pre-registered before fitting"},
        {"item": "step5_library_versions", "value": str(me.get("library_versions", "")),
         "note": "HW MLE differs across SciPy/NumPy versions"},
        {"item": "precision_rules", "value": "source cents (integer); USD 2dp in "
         "outputs; ratios full float; canonical hash quantises money 0.01, ratios 1e-6",
         "note": "no financial value altered for hashing"},
    ]
    for k, v in jobs.items():
        rows.append({"item": f"job:{k}", "value": json.dumps(v), "note": "Databricks job"})
    for t, c in sorted(counts.items()):
        rows.append({"item": f"table:{t}", "value": str(c), "note": "row count at Step 6"})
    return [{**r, "snapshot_id": snapshot} for r in rows]


# --------------------------------------------------------------------------- serving
def serving(T: dict[str, pd.DataFrame], extra: dict[str, pd.DataFrame],
            passports: list[dict[str, Any]], claims: list[dict[str, Any]],
            snapshot: str) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    pdx = extra["property_totals"].iloc[0]
    runs = T["optimization_runs"][T["optimization_runs"].role == "baseline"].set_index("mode")
    fc = T["forecast_baseline_comparison"].set_index("subset").loc["all"]
    ab = T["council_ablation_results"].set_index("configuration")
    k = [
        ("coin_in_usd", float(pdx.coin_in), "USD", "sum(property_day.coin_in_usd)",
         "CLM-REC-R03"),
        ("house_win_usd", float(pdx.house_win), "USD", "sum(property_day.house_win_usd)",
         "CLM-REC-R01"),
        ("theo_usd", float(pdx.theo), "USD", "sum(property_day.theo_usd)", "CLM-REC-R08"),
        ("observed_hold", float(pdx.house_win) / float(pdx.coin_in), "fraction",
         "sum(house_win)/sum(coin_in)", "CLM-REC-R01"),
        ("reconciliation_checks_passed", float((T["reconciliation_results"].status
                                                == "pass").sum()), "count of 14",
         "reconciliation_results", "CLM-REC-R01"),
        ("evidence_portfolio_cost", float(runs.loc["evidence_supported", "total_cost"]),
         "USD", "optimization_runs", "CLM-PF-baseline-evidence_supported"),
        ("evidence_portfolio_modeled_net", float(runs.loc["evidence_supported",
                                                          "net_benefit"]),
         "USD (modeled)", "optimization_runs", "CLM-PF-baseline-evidence_supported"),
        ("conditional_portfolio_cost", float(runs.loc["conditional", "total_cost"]), "USD",
         "optimization_runs", "CLM-PF-baseline-conditional"),
        ("conditional_portfolio_modeled_net", float(runs.loc["conditional", "net_benefit"]),
         "USD (modeled)", "optimization_runs", "CLM-PF-baseline-conditional"),
        ("forecast_mae_improvement_pct", float(fc.mae_improvement_pct), "%",
         "forecast_baseline_comparison (Databricks run)", "CLM-FORECAST"),
        ("council_independent_objections_gossip_on",
         float(ab.loc["D_six_whisper_network", "independent_objections"]), "count",
         "council_ablation_results", "CLM-WHISPER-EVAL"),
    ]
    dash: dict[str, pd.DataFrame] = {}
    dash["dash_executive_kpis"] = pd.DataFrame(
        [{"kpi": a, "value": b, "unit": c, "formula": d, "claim_id": e,
          "period": "2025-01-01..2025-06-30", "snapshot_id": snapshot} for a, b, c, d, e in k])
    mc = extra["machine_comparison"].copy()
    keep = ["machine_id", "zone_id", "config_id", "manufacturer", "house_win_usd", "theo_usd",
            "coin_in_usd", "luck_z", "hit_rate_z_cfg", "available_hours", "availability_rate",
            "theo_per_available_hour", "rank_raw", "rank_luck_aware", "rank_vs_peers",
            "p_bottom_luck_aware", "explanation"]
    dash["dash_machine_intelligence"] = mc[[c for c in keep if c in mc.columns]].assign(
        snapshot_id=snapshot)
    al = T["portfolio_allocations"].merge(
        T["optimization_runs"][["run_id", "portfolio_id", "role", "mode", "portfolio",
                                "total_cost", "net_benefit", "unspent_budget"]],
        on=["run_id", "portfolio_id", "role", "mode"])
    dash["dash_investment_portfolios"] = al.assign(
        line_id=[sid("PL", a, b, c) for a, b, c in zip(al.portfolio_id, al.role,
                                                        al.investment_id, strict=True)],
        snapshot_id=snapshot)
    sc = T["scenario_results"][["scenario_id", "scenario_kind", "description",
                                "optimal_portfolio", "optimal_net_benefit", "regret",
                                "baseline_still_optimal"]].assign(row_type="scenario")
    rv = T["decision_reversals"][T["decision_reversals"].reversal_found][
        ["assumption_id", "mode", "interval_low", "interval_high", "original_portfolio",
         "replacement_portfolio", "risk_class"]].assign(row_type="reversal")
    rv["scenario_id"] = [sid("RV", a, b, c) for a, b, c in
                         zip(rv.assumption_id, rv["mode"], rv.interval_low, strict=True)]
    dash["dash_scenario_surface"] = pd.concat([sc, rv], ignore_index=True).assign(
        snapshot_id=snapshot)
    ev = extra["council_events"]
    dash["dash_council_activity"] = ev.assign(
        event_id=[sid("CE", a, b) for a, b in zip(ev.config, ev.sequence, strict=True)],
        snapshot_id=snapshot)
    dash["dash_evidence_validation"] = pd.DataFrame(claims)
    dash["dash_model_evaluation"] = extra["holdout_predictions"][
        ["gaming_date", "actual", "baseline_pred", "candidate_pred", "candidate_lo80",
         "candidate_hi80", "horizon_days", "weekday", "is_event_day",
         "evaluation_run_id"]].assign(snapshot_id=snapshot)
    dash["dash_decision_passports"] = pd.DataFrame(passports)
    meta = {
        "dash_executive_kpis": ("kpi", "kpi", "period"),
        "dash_machine_intelligence": ("machine", "machine_id", "zone_id, manufacturer, "
                                      "config_id, explanation"),
        "dash_investment_portfolios": ("portfolio x action line", "line_id",
                                       "mode, role, portfolio_id"),
        "dash_scenario_surface": ("scenario or reversal", "scenario_id",
                                  "row_type, scenario_kind, mode"),
        "dash_council_activity": ("council event", "event_id", "config, event_type, actor"),
        "dash_evidence_validation": ("material claim", "claim_id",
                                     "category, evidence_classification"),
        "dash_model_evaluation": ("holdout gaming day", "gaming_date", "weekday, "
                                  "is_event_day"),
        "dash_decision_passports": ("portfolio x action", "passport_id",
                                    "portfolio_mode, action_type_id"),
    }
    manifest = []
    for name, df in dash.items():
        grain, key, dims = meta[name]
        manifest.append({"dataset": name, "row_grain": grain, "primary_key": key,
                         "rows": len(df), "key_unique": bool(df[key].is_unique),
                         "filters": dims, "units": "USD unless stated; modeled values "
                         "labelled", "snapshot_id": snapshot,
                         "null_policy": "nulls mean unknown/not applicable, never zero",
                         "validation_status": "VALIDATED" if df[key].is_unique else "FAILED"})
    return dash, manifest


# --------------------------------------------------------------------------- semantic
def semantic_contract(T: dict[str, pd.DataFrame], dash: dict[str, pd.DataFrame],
                      claims: list[dict[str, Any]], snapshot: str) -> dict[str, Any]:
    pp = dash["dash_decision_passports"]
    ent = {
        "machine": sorted(dash["dash_machine_intelligence"].machine_id),
        "zone": sorted(dash["dash_machine_intelligence"].zone_id.dropna().unique()),
        "portfolio": sorted(T["optimization_runs"].portfolio_id.unique()),
        "scenario": sorted(T["scenario_results"].scenario_id),
        "assumption": sorted(T["intervention_assumptions"].assumption_id),
        "claim": sorted(c["claim_id"] for c in claims),
        "agent": sorted(T["agent_claims"].agent_id.unique()),
        "action": sorted(T["action_catalog"].action_type_id),
        "passport": sorted(pp.passport_id),
    }
    ev_pf = T["optimization_runs"][(T["optimization_runs"].role == "baseline") & (
        T["optimization_runs"]["mode"] == "evidence_supported")].iloc[0]
    co_pf = T["optimization_runs"][(T["optimization_runs"].role == "baseline") & (
        T["optimization_runs"]["mode"] == "conditional")].iloc[0]
    stat = T["agent_claims"][(T["agent_claims"].config == "B_WHISPER_NETWORK")
                             & (T["agent_claims"].agent_id == "AG1_STATISTICIAN")
                             & (T["agent_claims"].role == "primary")].iloc[0]
    tests = [
        ("Why is M-1158 underperforming?", "get_evidence", {"machine": "M-1158"},
         "CLM-EV-1C684B792E7B", "payout frequency above game math (hit-rate z 124)"),
        ("What supports the promotion recommendation?", "get_evidence",
         {"portfolio": ev_pf.portfolio_id}, "CLM-ASM-A08_promo_excess_theo_per_day",
         "two past promotions, associational"),
        ("Why is the $5,281/day threshold important?", "explain_reversal",
         {"assumption": "A08_promo_excess_theo_per_day"}, "CLM-PROMO-CAUSAL",
         "promotion break-even; weaker event $5,016 sits below it"),
        ("What happens if promotion evidence is invalid?", "explain_reversal",
         {"assumption": "A08_promo_excess_theo_per_day"}, "evidence_impact_results",
         "evidence portfolio becomes HOLD"),
        ("What did the Statistician challenge?", "open_council_challenge",
         {"claim": stat.claim_id}, stat.claim_id, "weaker promotion 1.08 SD of noise"),
        ("Did gossip improve portfolio decisions?", "show_model_validation",
         {"claim": "CLM-WHISPER-EVAL"}, "CLM-WHISPER-EVAL", "no: identical portfolios"),
        ("Why is the conditional portfolio more uncertain?", "compare_portfolios",
         {"portfolio": [ev_pf.portfolio_id, co_pf.portfolio_id]},
         "CLM-PF-baseline-conditional", "extra lines rest on planning assumptions"),
        ("What did the forecasting model achieve?", "show_model_validation",
         {"claim": "CLM-FORECAST"}, "CLM-FORECAST", "beat weekday-mean baseline on MAE"),
        ("Which recommendation has the greatest tested regret?", "explain_reversal",
         {"claim": "CLM-REGRET"}, "CLM-REGRET", "max regret $3,636 (moves keep demand)"),
        ("What could change our investment decision?", "explain_reversal",
         {"portfolio": co_pf.portfolio_id}, "decision_reversals",
         "promotion excess, inspection probability, move transfer, wayfinding uplift"),
        ("How much did the casino win on M-9999?", "select_entity", {"machine": "M-9999"},
         None, "UNAVAILABLE: unknown machine id"),
        ("Will promotions definitely increase revenue?", "get_evidence",
         {"claim": "CLM-PROMO-CAUSAL"}, "CLM-PROMO-CAUSAL",
         "UNCERTAIN: causal effect not identified"),
    ]
    return {
        "contract_version": "ask-the-house-v1", "snapshot_id": snapshot,
        "rules": ["Answers only from serving datasets; never invent numbers",
                  "No generated SQL; only the intents below with validated entity ids",
                  "Unknown ids -> UNAVAILABLE; unidentified causal effects -> UNCERTAIN"],
        "entities": ent,
        "synonyms": {"theo": "theoretical win", "hold": "observed_hold",
                     "promo": "A-PROMO", "promotion weekend": "A-PROMO",
                     "back forty": "Z-B40", "center pit": "Z-PIT",
                     "high limit": "Z-HL", "gossip": "Whisper Network",
                     "break-even": "A08 reversal boundary", "inspection": "A-INSPECT",
                     "move": "A-MOVE-MACHINE"},
        "metrics": dash["dash_executive_kpis"][["kpi", "unit", "formula", "claim_id"]]
        .to_dict("records"),
        "intents": {
            "select_entity": {"entity_type": list(ent), "id": "string (must exist)"},
            "set_filters": {"zone": "zone", "machine": "machine", "portfolio": "portfolio",
                            "scenario": "scenario", "period": "2025-01-01..2025-06-30"},
            "get_evidence": {"claim|machine|portfolio|assumption": "id"},
            "compare_portfolios": {"portfolio": "list[portfolio id]"},
            "open_council_challenge": {"claim": "claim id"},
            "explain_reversal": {"assumption|portfolio|claim": "id"},
            "show_model_validation": {"claim": "claim id"},
            "navigate_dashboard": {"view": ["command_center", "council_chamber",
                                            "whisper_network", "evidence_observatory",
                                            "parallel_universes", "verdict"]}},
        "test_contracts": [{"question": q, "intent": i, "params": p, "answer_record": rec,
                            "expected": exp} for q, i, p, rec, exp in tests],
    }


def resolve(contract: dict[str, Any], entity_type: str, value: str) -> str:
    """Strict resolver for the NLP layer: unknown entity types or ids are rejected."""
    if entity_type not in contract["entities"]:
        raise KeyError(f"unknown entity type {entity_type!r}")
    v = contract["synonyms"].get(str(value).lower(), value)
    if v not in contract["entities"][entity_type]:
        raise KeyError(f"unknown {entity_type} id {value!r}")
    return v


def scan_public(df: pd.DataFrame) -> list[str]:
    bad = [c for c in df.columns if PERSONAL_COLUMNS.search(c)]
    text = df.astype(str).to_csv(index=False)
    if SECRET.search(text):
        bad.append("secret-like content")
    return bad
