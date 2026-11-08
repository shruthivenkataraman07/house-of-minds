"""Evidence Vault builders. Every row is derived from persisted Step 1-5 records.

Nothing here computes new financial results: portfolio numbers come from Step 3 tables,
council results from Step 4, model results from Step 5. Re-optimisation for invalidation
uses the existing Step 3 `invalidation_test`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

from vault.graph import Graph, Node

PASSPORT_SCHEMA = "passport-v1"
HORIZON = "2025-07-01..2025-07-30"
DECISION_DATE = "2025-07-01"
STATUS = ["VERIFIED_OBSERVATION", "VERIFIED_ARITHMETIC", "STATISTICAL_ESTIMATE",
          "MODELED_SCENARIO", "PLANNING_ASSUMPTION", "CAUSAL_EFFECT_NOT_IDENTIFIED",
          "RETRACTED", "INVALIDATED", "UNRESOLVED"]


def jl(x: Any) -> Any:
    """Parse a JSON-encoded column value; pass through anything else."""
    if isinstance(x, str) and x[:1] in "[{":
        try:
            return json.loads(x)
        except json.JSONDecodeError:
            return x
    return x


def sid(prefix: str, *parts: object) -> str:
    return prefix + "-" + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[
        :10].upper()


def split(x: Any) -> list[str]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return []
    return [s for s in str(x).split(",") if s]


# --------------------------------------------------------------------------- passports
def build_passports(T: dict[str, pd.DataFrame], snapshot: str) -> list[dict[str, Any]]:
    runs = T["optimization_runs"][T["optimization_runs"].role == "baseline"]
    alloc = T["portfolio_allocations"]
    cands = T["investment_candidates"].set_index("investment_id")
    links = T["decision_evidence_links"]
    revs = T["decision_reversals"]
    scen = T["scenario_results"]
    claims = T["agent_claims"][T["agent_claims"].config == "B_WHISPER_NETWORK"]
    plans = T["action_measurement_plans"].set_index("action_id")
    cat = T["action_catalog"].set_index("action_type_id")
    impact5 = T["decision_model_impact"]
    eval_id = str(T["model_evaluation_runs"].evaluation_run_id.iloc[0])
    alts = T["optimization_runs"][T["optimization_runs"].role != "baseline"]
    out = []
    for r in runs.itertuples():
        lines = alloc[(alloc.run_id == r.run_id) & (alloc.portfolio_id == r.portfolio_id)
                      & (alloc["role"] == "baseline")]
        for ln in lines.itertuples():
            c = cands.loc[ln.investment_id]
            asm = split(c.dependencies)
            ev = sorted(set(split(c.evidence_ids)) | set(
                links[(links.portfolio_id == r.portfolio_id)
                      & (links.investment_id == ln.investment_id)].evidence_id.dropna()))
            rv = revs[(revs.reversal_found) & (revs.assumption_id.isin(asm))
                      & (revs["mode"] == r.mode)]
            cc = claims[(claims.target_investment == ln.investment_id)
                        | (claims.target_assumption.isin(asm))]
            atype = c.action_type
            plan_id = f"MP-{atype}" if atype in plans.index else None
            status = c.benefit_status
            eff_class = {"EVIDENCE_ESTIMATE": "STATISTICAL_ESTIMATE (associational)",
                         "ASSUMPTION_REQUIRED": "PLANNING_ASSUMPTION"}.get(status, status)
            out.append({
                "passport_id": sid("PP", snapshot, r.portfolio_id, ln.investment_id),
                "passport_schema_version": PASSPORT_SCHEMA, "portfolio_id": r.portfolio_id,
                "portfolio_mode": r.mode, "portfolio_signature": r.portfolio,
                "decision_run_id": r.run_id, "snapshot_id": snapshot,
                "decision_horizon": HORIZON, "decision_date": DECISION_DATE,
                "action_catalog_id": "action_catalog (official, 13 actions)",
                "action_type_id": atype, "action_name": str(cat.loc[atype, "name"]),
                "investment_id": ln.investment_id, "target_entity": c.target_entity,
                "quantity": int(ln.quantity), "unit_cost": float(ln.unit_cost),
                "total_cost": float(ln.line_cost),
                "portfolio_total_cost": float(r.total_cost),
                "remaining_budget": float(r.unspent_budget),
                "modeled_incremental_effect": float(c.contribution_gain) * int(ln.quantity),
                "modeled_net_contribution": float(ln.line_net),
                "portfolio_modeled_net": float(r.net_benefit),
                "effect_classification": eff_class,
                "assumption_ids": ",".join(asm), "evidence_ids": ",".join(ev),
                "source_query_ids": ",".join(sorted(set(
                    links[links.investment_id == ln.investment_id].evidence_source_tables
                    .dropna()))),
                "scenario_ids": ",".join(scen.scenario_id),
                "reversal_ids": ",".join(sid("RV", x.assumption_id, x["mode"], x.interval_low)
                                         for _, x in rv.iterrows()),
                "reversal_summary": "; ".join(
                    f"{x.assumption_id} flips at [{x.interval_low:.4g}, {x.interval_high:.4g}]"
                    for _, x in rv.iterrows()) or "no reversal found in tested range",
                "council_claim_ids": ",".join(cc.claim_id),
                "verification_result_ids": ",".join(cc.claim_id),
                "model_evaluation_ids": eval_id if atype == "A-PROMO" else "",
                "measurement_plan_id": plan_id,
                "alternative": "; ".join(f"{a.role}: {a.portfolio} (${a.net_benefit:,.0f})"
                                         for a in alts.itertuples() if a.mode == r.mode)
                or ("evidence-supported portfolio " + str(
                    runs[runs["mode"] != r.mode].portfolio.iloc[0])),
                "limitations": str(c.causal_status) + (
                    "; promotion uplift associational (2 events, no control)"
                    if atype == "A-PROMO" else ""),
                "forecast_link": (json.dumps(impact5[impact5["mode"] == r.mode][
                    ["counterfactual_method", "statistic", "a08_value", "portfolio"]]
                    .to_dict("records")) if atype == "A-PROMO" else None),
                "data_as_of": "2025-06-30 (gaming date)",
                "source_run_ids": f"step3:{r.run_id}",
                "validation_status": "VERIFIED" if r.verification == "OK" else "UNVERIFIED",
                "financial_field_note": "line net is additive: portfolio net = sum of line "
                                        "nets (Step 3 linear objective)"})
    return out


# --------------------------------------------------------------------------- claims
def build_claims(T: dict[str, pd.DataFrame], snapshot: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(cat: str, cid: str, text: str, decision: str, table: str, query: str,
            result: Any, alt: str, lim: str, status: str, verification: str,
            evidence: str = "", assumptions: str = "", sensitivity: str = "",
            contradicting: str = "", original: str = "") -> None:
        rows.append({"claim_id": cid, "category": cat, "claim_text": text,
                     "decision": decision, "source_table": table, "query_ref": query,
                     "result": json.dumps(result, default=str),
                     "alternative_explanation": alt, "limitation": lim,
                     "evidence_classification": status, "verification_status": verification,
                     "supporting_records": evidence, "contradicting_evidence": contradicting,
                     "assumptions": assumptions, "decision_sensitivity": sensitivity,
                     "original_statement": original, "snapshot_id": snapshot,
                     "data_as_of": "2025-06-30"})

    for r in T["reconciliation_results"].itertuples():
        add("financial_reconciliation", f"CLM-REC-{r.test_id}", r.description,
            "all financial figures", r.input_data, f"pipelines.validation.reconciliation."
            f"{r.test_id}", jl(r.calculated_result),
            "n/a: arithmetic identity recomputed from source tables", r.explanation,
            "VERIFIED_ARITHMETIC", r.status.upper())
    led = T["evidence_ledger"]
    cat_map = {"machine_performance": "machine_performance", "investigations": None,
               "modeling": "forecast_model", "validation": None}
    for r in led.itertuples():
        if r.calculation_id.startswith(("reconciliation.", "contract.")):
            continue
        res = jl(r.result)
        calc = r.calculation_id
        cat = ("downtime" if "downtime" in calc else "comp_economics" if "comp" in calc
               else "zone_demand" if "walkway" in calc else "machine_performance"
               if "payout" in calc or "machine_performance" in calc else
               cat_map.get(r.domain) or r.domain)
        alt = (res.get("competing_explanation", "") if isinstance(res, dict) else "") or (
            "rankings depend on exposure, luck and configuration (see decomposition)"
            if "machine_performance" in calc else "see limitation")
        state = {"reconciled": "VERIFIED_ARITHMETIC", "tested": "STATISTICAL_ESTIMATE",
                 "descriptive": "VERIFIED_OBSERVATION"}.get(r.validation_state,
                                                            "UNRESOLVED")
        lim = "; ".join(x for x in (jl(r.limitations) or []) if x) or "see source"
        add(cat, f"CLM-{r.evidence_id}", r.claim, "investment candidates",
            ",".join(jl(r.source_tables) or []), calc, res, alt, lim, state,
            "VERIFIED", evidence=r.evidence_id)
    for r in T["intervention_assumptions"].itertuples():
        st = ("STATISTICAL_ESTIMATE" if r.status == "EVIDENCE_ESTIMATE"
              else "PLANNING_ASSUMPTION")
        add("assumptions", f"CLM-ASM-{r.assumption_id}",
            f"{r.description}: {r.value:.6g} {r.unit} (tested {r.low:.6g}-{r.high:.6g})",
            "Step 3 optimiser input", "intervention_assumptions",
            f"optimization.investment_model.{r.assumption_id}",
            {"value": r.value, "low": r.low, "high": r.high, "unit": r.unit}, r.source,
            f"causal status: {r.causal_status}", st,
            "VERIFIED" if st == "STATISTICAL_ESTIMATE" else "UNRESOLVED",
            evidence=r.evidence_ids, assumptions=r.assumption_id)
    for r in T["investment_candidates"].itertuples():
        add("investment_costs", f"CLM-COST-{r.investment_id}",
            f"{r.investment_id} costs ${r.unit_cost:,.2f}/unit with "
            f"{r.effective_days_within_horizon} effective days; modeled net "
            f"{'n/a' if pd.isna(r.benefit_base) else f'${r.benefit_base:,.0f}'}",
            r.investment_id, "investment_candidates + action_catalog",
            "optimization.action_catalog.unit_cost_in_horizon_cents",
            {"unit_cost": r.unit_cost, "benefit_low": r.benefit_low,
             "benefit_base": r.benefit_base, "benefit_high": r.benefit_high,
             "status": r.benefit_status}, "Benefit depends on stated assumptions",
            f"{r.benefit_status}; {r.causal_status}", "VERIFIED_ARITHMETIC"
            if r.benefit_status in ("NEGATIVE_AT_BEST_CASE", "INELIGIBLE",
                                    "NOT_IDENTIFIABLE") else "MODELED_SCENARIO",
            "VERIFIED", evidence=r.evidence_ids, assumptions=r.dependencies)
    for r in T["optimization_runs"].itertuples():
        add("portfolio_selection", f"CLM-PF-{r.role}-{r.mode}",
            f"{r.mode} {r.role} portfolio: {r.portfolio} costs ${r.total_cost:,.0f}, "
            f"modeled net ${r.net_benefit:,.0f}", r.portfolio_id, "optimization_runs",
            "optimization.portfolio.optimise (SciPy MILP)",
            {"cost": r.total_cost, "net": r.net_benefit, "unspent": r.unspent_budget},
            "Different assumption values select different portfolios (see reversals)",
            "Modeled contribution, not realised profit", "MODELED_SCENARIO",
            "VERIFIED" if r.verification == "OK" else "UNVERIFIED")
    for r in T["decision_reversals"][T["decision_reversals"].reversal_found].itertuples():
        add("decision_reversals", sid("CLM-RV", r.assumption_id, r.mode, r.interval_low),
            f"{r.mode}: decision flips when {r.assumption_id} crosses "
            f"[{r.interval_low:.6g}, {r.interval_high:.6g}]", r.original_portfolio_id,
            "decision_reversals", "optimization.decision_analysis.decision_reversals",
            {"from": r.original_portfolio, "to": r.replacement_portfolio,
             "risk": r.risk_class}, "Boundary location depends on other assumptions",
            r.limitations, "MODELED_SCENARIO", "VERIFIED (re-optimised both sides)",
            evidence=r.evidence_ids, assumptions=r.assumption_id, sensitivity=r.risk_class)
    rg = T["portfolio_regret"].iloc[0]
    add("scenario_regret", "CLM-REGRET", f"Baseline optimal in "
        f"{int(rg.baseline_optimal_count)}/{int(rg.scenarios)} scenarios; max regret "
        f"${rg.max_regret:,.0f}; median ${rg.median_regret:,.0f}", "conditional portfolio",
        "portfolio_regret", "optimization.decision_analysis.regret_summary",
        {"max": rg.max_regret, "median": rg.median_regret, "mean": rg.mean_regret_unweighted},
        "Scenario set is not exhaustive", "No scenario probabilities; unweighted",
        "MODELED_SCENARIO", "VERIFIED")
    cl = T["agent_claims"]
    vr = T["claim_verification_results"].set_index(["config", "claim_id"])
    b = cl[cl.config == "B_WHISPER_NETWORK"]
    for r in b.itertuples():
        v = vr.loc[("B_WHISPER_NETWORK", r.claim_id)]
        if r.retracted:
            st, ver = "RETRACTED", "RETRACTED"
            corr = b[b.origin_claim_id == r.claim_id]
            contra = "; ".join(corr.claim_id + ": " + corr.statement)
        elif r.causal_claim:
            st, ver, contra = "CAUSAL_EFFECT_NOT_IDENTIFIED", v.verdict, ""
        else:
            st = {"VERIFIED": "VERIFIED_OBSERVATION", "INCONCLUSIVE": "UNRESOLVED"}.get(
                v.verdict, "INVALIDATED")
            ver, contra = v.verdict, ""
        add("guest_behavior" if r.agent_id == "AG4_GUEST" else "agent_challenges",
            r.claim_id, r.statement, r.target_investment,
            "agent_claims + claim_verification_results", r.query_refs or "none",
            {"numeric": r.numeric_result, "unit": r.numeric_unit, "agent": r.agent_id,
             "action": r.action, "relevance": v.decision_relevance},
            r.alternative_explanation or "not stated by agent",
            r.limitation or "rule-based agent; see verifier reasons", st, ver,
            evidence=r.evidence_ids, contradicting=contra,
            original=r.statement if r.retracted else "")
    ab = T["council_ablation_results"].set_index("configuration")
    add("whisper_network", "CLM-WHISPER-EVAL", "Gossip gave equal independent objections "
        f"({int(ab.loc['C_six_no_gossip','independent_objections'])} vs "
        f"{int(ab.loc['D_six_whisper_network','independent_objections'])}), one retraction "
        "and 3 extra evidence checks; identical portfolios", "council design",
        "council_ablation_results", "scripts/run_step5.py recompute()",
        ab.reset_index()[["configuration", "independent_objections", "retractions",
                          "new_evidence_checks", "decision_changes"]].to_dict("records"),
        "Single deterministic comparison; rule-based agents",
        "Not a statistical trial; repeated runs are identical", "VERIFIED_OBSERVATION",
        "VERIFIED")
    fc = T["forecast_baseline_comparison"].set_index("subset")
    add("forecast_model", "CLM-FORECAST", "Holt-Winters beat the weekday-mean baseline on "
        f"the May-Jun holdout: MAE ${fc.loc['all','candidate_mae']:,.0f} vs "
        f"${fc.loc['all','baseline_mae']:,.0f}", "promotion counterfactual",
        "forecast_baseline_comparison + holdout_predictions",
        "models.forecasting.run_forecast_evaluation",
        fc.reset_index()[["subset", "baseline_mae", "candidate_mae",
                          "mae_improvement_pct", "candidate_coverage80"]].to_dict("records"),
        "Event days are worse; level shift in May-Jun", "80% intervals under-cover; MLE "
        "varies with SciPy/NumPy (local MAE 5,836 vs Databricks 5,552)",
        "STATISTICAL_ESTIMATE", "VERIFIED (chronological holdout)")
    di = T["decision_model_impact"]
    w = di[(di["mode"] == "evidence_supported") & (di.statistic == "low")]
    add("forecast_decision_impact", "CLM-FORECAST-DECISION",
        "At the weaker promotion, the decision depends on the counterfactual method",
        "INV-PROMO", "decision_model_impact", "scripts/run_step5.py decision impact",
        w[["counterfactual_method", "a08_value", "portfolio"]].to_dict("records"),
        "Symmetric/past-only averages vs Holt-Winters counterfactual",
        "Associational; 2 events", "MODELED_SCENARIO", "VERIFIED")
    a08 = T["intervention_assumptions"].set_index("assumption_id").loc[
        "A08_promo_excess_theo_per_day"]
    add("promotions", "CLM-PROMO-CAUSAL", "Promotions cause the observed weekend uplift",
        "INV-PROMO", "property_day, events",
        "optimization.investment_model.promo_effect + council tools",
        {"events": 2, "low": a08.low, "mean": a08.value, "high": a08.high,
         "breakeven": 5281.1, "weekend_sd": 4649},
        "Season, citywide events and displacement could produce the same pattern",
        "Two events, no control group: causal effect not identified",
        "CAUSAL_EFFECT_NOT_IDENTIFIED", "UNRESOLVED", sensitivity="HIGH: weaker event "
        "($5,016) below break-even ($5,281) under the Step 3 window")
    return rows


# --------------------------------------------------------------------------- graph
def build_graph(T: dict[str, pd.DataFrame], claims: list[dict[str, Any]],
                passports: list[dict[str, Any]], snapshot: str) -> Graph:
    g = Graph()

    def n(nid: str, typ: str, label: str, step: str, ref: str) -> str:
        g.add_node(Node(nid, typ, label[:200], step, ref, snapshot))
        return nid

    srcs = set()
    for r in T["evidence_ledger"].itertuples():
        for s in jl(r.source_tables) or []:
            srcs.add(s)
    for s in sorted(srcs | {"property_day", "calendar_day", "events", "action_catalog"}):
        n(f"TBL:{s}", "source_table", s, "step1", f"workspace.house_of_minds.{s}")
    for r in T["evidence_ledger"].itertuples():
        e = n(f"EV:{r.evidence_id}", "evidence", r.claim, "step1-2", r.calculation_id)
        for s in jl(r.source_tables) or []:
            g.add_edge(e, f"TBL:{s}", "DERIVED_FROM")
    for r in T["intervention_assumptions"].itertuples():
        a = n(f"ASM:{r.assumption_id}", "assumption", r.description, "step3", r.status)
        evs = split(r.evidence_ids)
        for e in evs:
            g.add_edge(a, f"EV:{e}", "DERIVED_FROM" if r.status == "EVIDENCE_ESTIMATE"
                       else "SUPPORTS")
        if r.assumption_id == "A08_promo_excess_theo_per_day":
            for s in ("property_day", "calendar_day", "events"):
                g.add_edge(a, f"TBL:{s}", "DERIVED_FROM")
    for r in T["investment_candidates"].itertuples():
        c = n(f"CAND:{r.investment_id}", "investment_candidate", r.investment_id, "step3",
              r.benefit_status)
        g.add_edge(c, "TBL:action_catalog", "DERIVED_FROM")
        for a in split(r.dependencies):
            g.add_edge(c, f"ASM:{a}", "ASSUMES")
    for r in T["optimization_runs"].itertuples():
        p = n(f"PF:{r.portfolio_id}", "portfolio", f"{r.mode} {r.role}: {r.portfolio}",
              "step3", r.run_id)
        for a in T["portfolio_allocations"][(T["portfolio_allocations"].portfolio_id
                                             == r.portfolio_id)].investment_id.unique():
            g.add_edge(p, f"CAND:{a}", "USED_BY_OPTIMIZER")
    for r in T["scenario_results"].itertuples():
        s = n(f"SCN:{r.scenario_id}", "scenario", r.description, "step3", r.scenario_kind)
        for a in T["intervention_assumptions"].assumption_id:
            if a in str(r.modified_inputs):
                g.add_edge(s, f"ASM:{a}", "USED_IN_SCENARIO")
        g.add_edge(s, f"PF:{r.baseline_portfolio_id}", "USED_IN_SCENARIO")
    for r in T["decision_reversals"][T["decision_reversals"].reversal_found].itertuples():
        rv = n(sid("RV", r.assumption_id, r.mode, r.interval_low), "reversal",
               f"{r.assumption_id} [{r.interval_low:.4g},{r.interval_high:.4g}]", "step3",
               r.mode)
        g.add_edge(rv, f"ASM:{r.assumption_id}", "DERIVED_FROM")
        if f"PF:{r.original_portfolio_id}" in g.nodes:
            g.add_edge(rv, f"PF:{r.original_portfolio_id}", "AFFECTS_DECISION")
    cl = T["agent_claims"]
    for r in cl[cl.config == "B_WHISPER_NETWORK"].itertuples():
        c = n(f"CC:{r.claim_id}", "council_claim", r.statement, "step4", r.agent_id)
        v = n(f"VR:{r.claim_id}", "verification", f"verification of {r.claim_id}", "step4",
              "claim_verification_results")
        g.add_edge(c, v, "VERIFIED_BY")
        for e in split(r.evidence_ids):
            if f"EV:{e}" in g.nodes:
                g.add_edge(c, f"EV:{e}", "DERIVED_FROM")
        tgt = f"ASM:{r.target_assumption}"
        if tgt in g.nodes and r.action in ("CHALLENGE", "PROPOSE_SCENARIO",
                                           "FLAG_UNCERTAINTY", "REQUEST_EVIDENCE"):
            g.add_edge(c, tgt, "CHALLENGES")
        elif tgt in g.nodes and r.action == "SUPPORT":
            g.add_edge(c, tgt, "SUPPORTS")
        o = r.origin_claim_id
        if isinstance(o, str) and o and f"CC:{o}" in g.nodes:
            g.add_edge(c, f"CC:{o}", "CONTRADICTS" if r.action == "CHALLENGE" else "SUPPORTS")
    for r in cl[(cl.config == "B_WHISPER_NETWORK") & cl.retracted].itertuples():
        for x in cl[(cl.config == "B_WHISPER_NETWORK")
                    & (cl.origin_claim_id == r.claim_id)].itertuples():
            g.add_edge(f"CC:{r.claim_id}", f"CC:{x.claim_id}", "INVALIDATED_BY")
    me = n(f"MODEL:{T['model_evaluation_runs'].evaluation_run_id.iloc[0]}", "model_evaluation",
           "Holt-Winters vs weekday-mean holdout", "step5", "model_evaluation_runs")
    g.add_edge(me, "TBL:property_day", "DERIVED_FROM")
    g.add_edge(me, "ASM:A08_promo_excess_theo_per_day", "AFFECTS_DECISION")
    for reg in claims:
        k = n(f"CLAIM:{reg['claim_id']}", "registry_claim", reg["claim_text"], "step6",
              reg["source_table"])
        for e in split(reg["supporting_records"]):
            if f"EV:{e}" in g.nodes:
                g.add_edge(k, f"EV:{e}", "DERIVED_FROM")
        for a in split(reg["assumptions"]):
            if f"ASM:{a}" in g.nodes:
                g.add_edge(k, f"ASM:{a}", "ASSUMES")
    for pp in passports:
        m = n(f"METRIC:passport:{pp['passport_id']}", "dashboard_metric",
              f"passport {pp['investment_id']}", "step6", "dash_decision_passports")
        g.add_edge(m, f"PF:{pp['portfolio_id']}", "DISPLAYED_BY_METRIC")
    return g


def graph_tables(g: Graph, snapshot: str) -> tuple[list[dict[str, Any]],
                                                   list[dict[str, Any]]]:
    nodes = [{**vars(v), "snapshot_id": snapshot} for v in g.nodes.values()]
    edges = [{"edge_id": sid("E", f, t, k), "from_node": f, "to_node": t, "edge_type": k,
              "snapshot_id": snapshot} for f, t, k in sorted(g.edges)]
    return nodes, edges
