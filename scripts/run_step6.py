"""Step 6: The Evidence Vault (reads Steps 1-5 from Unity Catalog; writes derived tables).

Usage: uv run python scripts/run_step6.py   (or the Databricks job)
Prior-phase tables are read-only; documents are generated from registry records.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

try:
    _SCRIPT = Path(__file__).resolve()
except NameError:  # Databricks serverless exec()
    _SCRIPT = Path(sys.argv[0]).resolve()
ROOT = _SCRIPT.parents[1]
sys.path.insert(0, str(ROOT))

from typing import Any  # noqa: E402

import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402

from config.settings import get_settings  # noqa: E402
from optimization.action_catalog import ActionCatalog, SelectedAction, price_selection  # noqa: E402
from optimization.investment_model import build_model  # noqa: E402
from optimization.portfolio import MODE_EVIDENCE  # noqa: E402
from vault import build as B  # noqa: E402
from vault import extra as X  # noqa: E402

PRIOR = ["reconciliation_results", "machine_comparison", "evidence_ledger", "validation_summary",
         "investment_candidates", "intervention_assumptions", "optimization_runs",
         "portfolio_allocations", "scenario_results", "decision_reversals", "portfolio_regret",
         "decision_evidence_links", "optimizer_validation_summary", "council_runs",
         "agent_claims", "council_whispers", "claim_verification_results",
         "council_decision_events", "council_portfolio_impacts", "agent_reliability_summary",
         "council_validation_summary", "model_evaluation_runs", "holdout_predictions",
         "forecast_baseline_comparison", "decision_model_impact", "promotion_counterfactuals",
         "council_ablation_results", "agent_reliability_evaluation",
         "decision_robustness_results", "action_measurement_plans", "aibi_metric_definitions",
         "step5_validation_summary"]
LOAD = PRIOR + ["action_catalog"]
JOBS = {"step2": {"job_id": 976658855400592, "run_id": 411075602890645},
        "step3": {"job_id": 670548312985484, "run_id": 4424786631438},
        "step4": {"job_id": 15426832427505, "run_id": 410566497924336},
        "step5": {"job_id": 135772365852291, "run_id": 1048055762772498}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse-id")
    ap.add_argument("--catalog")
    ap.add_argument("--schema")
    ap.add_argument("--output-dir")
    ap.add_argument("--job-run-id", default="")
    args = ap.parse_args(argv)
    for flag, env in [("warehouse_id", "DATABRICKS_WAREHOUSE_ID"),
                      ("catalog", "DATABRICKS_CATALOG"), ("schema", "DATABRICKS_SCHEMA"),
                      ("output_dir", "HOM_OUTPUT_DIR")]:
        if getattr(args, flag):
            os.environ[env] = getattr(args, flag)
    get_settings.cache_clear()
    s = get_settings()
    t0 = time.time()
    out_root = Path(os.environ.get("HOM_OUTPUT_DIR", str(ROOT)))
    from backend.repositories.databricks_repo import DatabricksRepository
    repo = DatabricksRepository(s.databricks_warehouse_id or "", s.databricks_catalog,
                                s.databricks_schema, s.databricks_profile)
    tables = set(repo.list_tables())
    missing5 = [t for t in ["model_evaluation_runs", "holdout_predictions",
                            "forecast_baseline_comparison", "decision_model_impact",
                            "action_measurement_plans", "step5_validation_summary"]
                if t not in tables]
    T = {n: repo.query_df(f"SELECT * FROM {n}") for n in LOAD if n in tables}
    T = {k: v.drop(columns=[c for c in v.columns if c == "_rescued_data"])
         for k, v in T.items()}
    before = {t: len(T[t]) for t in PRIOR if t in T}
    snapshot = str(T["model_evaluation_runs"].source_snapshot.iloc[0])
    vault_run = B.sid("S6", snapshot, json.dumps(before, sort_keys=True))
    model = build_model(repo, ActionCatalog.load(repo))

    passports = B.build_passports(T, snapshot)
    claims = B.build_claims(T, snapshot)
    g = B.build_graph(T, claims, passports, snapshot)
    nodes, edges = B.graph_tables(g, snapshot)
    impacts = X.invalidation_impacts(g, model, snapshot)
    measure = X.measurement_register(T, snapshot)
    ai = X.ai_usage_audit(T, snapshot)
    extra = {
        "property_totals": repo.query_df(
            "SELECT sum(coin_in_usd)::DOUBLE coin_in, sum(house_win_usd)::DOUBLE house_win, "
            "sum(theo_usd)::DOUBLE theo FROM property_day"),
        "machine_comparison": T["machine_comparison"],
        "council_events": T["council_decision_events"].drop(columns=["payload"],
                                                            errors="ignore"),
        "holdout_predictions": T["holdout_predictions"],
    }
    dash, serving_manifest = X.serving(T, extra, passports, claims, snapshot)
    contract = X.semantic_contract(T, dash, claims, snapshot)
    repro = X.reproducibility_manifest(T, snapshot, before, JOBS)

    # ---- public-safe export -------------------------------------------------------------
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", snapshot)
    exp_dir = out_root / "exports" / f"public_snapshot_{safe}"
    exp_dir.mkdir(parents=True, exist_ok=True)
    export_problems = {}
    for name, df in dash.items():
        bad = X.scan_public(df)
        if bad:
            export_problems[name] = bad
            continue
        df.to_json(exp_dir / f"{name}.json", orient="records", date_format="iso",
                   default_handler=str)
    (exp_dir / "manifest.json").write_text(json.dumps(
        {"snapshot_id": snapshot, "vault_run_id": vault_run, "datasets": serving_manifest,
         "created_at_utc": datetime.now(UTC).isoformat(timespec="seconds")}, indent=1,
        default=str))
    sem_dir = out_root / "semantic"
    sem_dir.mkdir(exist_ok=True)
    (sem_dir / "ask_the_house_contract.json").write_text(json.dumps(contract, indent=1,
                                                                    default=str))

    # ---- persist ----------------------------------------------------------------------
    def put(name: str, rows: list[dict[str, Any]] | pd.DataFrame) -> None:
        df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
        df = df.copy()
        for c in df.columns:
            if df[c].dtype == object:
                df[c] = df[c].map(lambda v: v if v is None or isinstance(v, str)
                                  else json.dumps(v, default=str))
        df["vault_run_id"] = vault_run
        repo.write_table(name, pa.Table.from_pandas(df, preserve_index=False))

    put("decision_passports", passports)
    put("claims_evidence_registry", claims)
    put("evidence_dependency_nodes", nodes)
    put("evidence_dependency_edges", edges)
    put("evidence_impact_results", impacts)
    put("measurement_accountability", measure)
    put("ai_usage_audit", ai)
    put("reproducibility_manifest", repro)
    put("dashboard_serving_manifest", serving_manifest)
    for name, df in dash.items():
        put(name, df)

    # ---- generated documents -------------------------------------------------------------
    docs = out_root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    write_appendix(docs / "CLAIMS_AND_EVIDENCE_APPENDIX.md", claims)
    write_contract_doc(docs / "DASHBOARD_DATA_CONTRACT.md", serving_manifest, contract)
    write_repro(docs / "REPRODUCIBILITY_GUIDE.md", repro)
    write_ai(docs / "AI_USE_DISCLOSURE.md", ai)
    summary_words = write_readiness(docs / "FINAL_SUBMISSION_READINESS.md", T, dash, claims,
                                    missing5)

    # ---- gates --------------------------------------------------------------------------
    gates: list[dict[str, Any]] = []

    def gate(n: int, name: str, ok: bool | None, detail: Any) -> None:
        gates.append({"vault_run_id": vault_run, "snapshot_id": snapshot, "gate_no": n,
                      "gate": name, "status": "BLOCKED" if ok is None else
                      ("PASS" if ok else "FAIL"), "detail": json.dumps(detail, default=str)[
                          :900]})

    cat = T["action_catalog"].set_index("action_type_id")
    pp = pd.DataFrame(passports)
    runs = T["optimization_runs"]
    gate(1, "passports from real portfolio records",
         len(pp) > 0 and set(pp.portfolio_id) <= set(runs.portfolio_id), len(pp))
    cost_ok = all(abs(r.unit_cost - (cat.loc[r.action_type_id, "unit_cost_cents"]
                                     + cat.loc[r.action_type_id, "recurring_cost_cents_per_day"]
                                     * max(0, 30 - cat.loc[r.action_type_id, "lead_days"]))
                      / 100) < 0.005 and abs(r.total_cost - r.unit_cost * r.quantity) < 0.005
                  for r in pp.itertuples())
    gate(2, "costs reconcile with official catalog", cost_ok, "GUIDE formula per line")
    lim_ok = True
    for _pid, grp in pp.groupby("portfolio_id"):
        sel = [SelectedAction(action_type_id=r.action_type_id, quantity=int(r.quantity),
                              extra_cost_cents=0) for r in grp.itertuples()]
        merged: dict[str, int] = {}
        for x in sel:
            merged[x.action_type_id] = merged.get(x.action_type_id, 0) + x.quantity
        res = price_selection(model.catalog, [SelectedAction(action_type_id=k, quantity=v,
                                                             extra_cost_cents=0)
                                              for k, v in merged.items()])
        lim_ok &= res.valid and res.total_usd <= 100000 and res.action_types_used <= 3
        lim_ok &= abs(res.total_usd - grp.portfolio_total_cost.iloc[0]) < 0.01
    gate(3, "budget and action-type limits (types vs instances)", lim_ok,
         pp.groupby("portfolio_mode").action_type_id.nunique().to_dict())
    gate(4, "observed vs assumed effects distinguished",
         set(pp.effect_classification) <= {"STATISTICAL_ESTIMATE (associational)",
                                           "PLANNING_ASSUMPTION"}
         and not any("REALIZED" in x.upper() for x in pp.effect_classification), "")
    gate(5, "competing portfolios identifiable", all(pp.alternative.str.len() > 0), "")
    rv_ids = {B.sid("RV", r.assumption_id, r.mode, r.interval_low)
              for r in T["decision_reversals"].itertuples() if r.reversal_found}
    gate(6, "reversals link to optimizer results",
         all(set(B.split(x)) <= rv_ids for x in pp.reversal_ids), len(rv_ids))
    gate(7, "measurement plans attached", all(pp.measurement_plan_id.notna())
         and set(pp.measurement_plan_id) <= {m["measurement_plan_id"] for m in measure}, "")
    cdf = pd.DataFrame(claims)
    gate(8, "claims have source/query references",
         cdf.source_table.str.len().gt(0).all() and cdf.query_ref.str.len().gt(0).all(),
         len(cdf))
    rec = T["reconciliation_results"].set_index("test_id").calculated_result
    rec_ok = all(json.loads(cdf.set_index("claim_id").loc[f"CLM-REC-{t}", "result"])
                 == json.loads(v) for t, v in rec.items())
    gate(9, "claims have reproducible results",
         rec_ok and all(json.loads(x) is not None for x in cdf.result),
         "reconciliation claims equal their source records; all results parse")
    gate(10, "alternative explanations documented",
         cdf.alternative_explanation.str.len().gt(0).all(), "")
    gate(11, "limitations documented", cdf.limitation.str.len().gt(0).all(), "")
    gate(12, "evidence classifications valid", set(cdf.evidence_classification)
         <= set(B.STATUS), sorted(set(cdf.evidence_classification)))
    retr = cdf[cdf.evidence_classification == "RETRACTED"]
    gate(13, "retractions and invalidations preserved",
         len(retr) == 1 and retr.original_statement.str.len().gt(0).all()
         and retr.contradicting_evidence.str.len().gt(0).all(), retr.claim_id.tolist())
    ledger_ids = set(T["evidence_ledger"].evidence_id)
    refs = {e for x in cdf.supporting_records for e in B.split(x) if e.startswith("EV-")}
    gate(14, "claim references resolve", refs <= ledger_ids and not g.dangling(),
         {"unresolved": sorted(refs - ledger_ids), "dangling_edges": len(g.dangling())})
    ev_pf = runs[(runs.role == "baseline") & (runs["mode"] == MODE_EVIDENCE)].portfolio_id.iloc[0]
    up = g.upstream(f"PF:{ev_pf}")
    gate(15, "dependency graph traversal works",
         "ASM:A08_promo_excess_theo_per_day" in up and "TBL:property_day" in up
         and not g.derivation_cycles(), {"upstream_of_evidence_portfolio": len(up)})
    imp = pd.DataFrame(impacts)
    promo = imp[imp.case == "INV-PROMO-EVIDENCE"]
    opt_rows = promo[promo.affected_type == "optimizer_recompute"]
    gate(16, "invalidation impact reproducible",
         set(promo[promo.impact_class == "direct"].affected_node) >= {
             "CAND:INV-PROMO"} and (opt_rows.impact_class == "decision_changed").all(),
         opt_rows.meaning.tolist())
    pay = imp[(imp.case == "INV-PAYOUT-EVIDENCE") & (imp.affected_type
                                                     == "optimizer_recompute")]
    gate(17, "invalidation does not falsify unrelated decisions; repetition is not "
         "corroboration", set(pay.impact_class) == {"decision_changed", "decision_unchanged"}
         and int(T["council_ablation_results"].set_index("configuration").loc[
             "D_six_whisper_network", "independent_objections"]) == 3,
         pay.meaning.tolist())
    gate(18, "Step 5 availability checked", not missing5, {"missing": missing5})
    gate(19, "chronological holdout linked", "CLM-FORECAST" in set(cdf.claim_id)
         and len(T["holdout_predictions"]) == 61, 61)
    fc = T["forecast_baseline_comparison"].set_index("subset").loc["all"]
    re_mae = (T["holdout_predictions"].candidate_pred - T["holdout_predictions"].actual).abs(
    ).mean()
    gate(20, "model performance not invented", abs(re_mae - fc.candidate_mae) < 1e-6,
         {"recomputed": re_mae, "stored": fc.candidate_mae})
    gate(21, "rule-based agent status accurate",
         any(r["status"] == "NOT LLM agents" for r in ai)
         and set(T["council_runs"].execution_mode) == {"RULE_BASED"}, "")
    w = cdf.set_index("claim_id").loc["CLM-WHISPER-EVAL"]
    gate(22, "gossip evidence-hygiene finding preserved", "retraction" in w.claim_text, "")
    gate(23, "no portfolio improvement attributed to gossip", "identical portfolios"
         in w.claim_text, "")
    gate(24, "serving datasets have documented grains",
         all(m["row_grain"] and m["key_unique"] for m in serving_manifest),
         [(m["dataset"], m["rows"]) for m in serving_manifest])
    k = dash["dash_executive_kpis"].set_index("kpi").value
    mi = dash["dash_machine_intelligence"]
    pl = dash["dash_investment_portfolios"]
    agg_ok = (abs(mi.coin_in_usd.sum() - k["coin_in_usd"]) < 1
              and abs(mi.house_win_usd.sum() - k["house_win_usd"]) < 1
              and all(abs(grp.line_cost.sum() - grp.total_cost.iloc[0]) < 0.01
                      for _, grp in pl.groupby(["run_id", "portfolio_id", "role"])))
    gate(25, "serving aggregates reconcile (no double counting)", agg_ok,
         {"machines_coin_in": mi.coin_in_usd.sum(), "kpi": k["coin_in_usd"]})
    gate(26, "stable shared identifiers", all(m["key_unique"] for m in serving_manifest)
         and pp.passport_id.is_unique, "")
    gate(27, "snapshot manifest versioned", snapshot.startswith("chf-v1:"), snapshot)
    gate(28, "public exports free of secrets and personal data", not export_problems,
         export_problems or "clean")
    try:
        X.resolve(contract, "machine", "M-9999")
        reject = False
    except KeyError:
        reject = True
    ok_ids = all(X.resolve(contract, "machine", "M-1158") == "M-1158" for _ in [0]) and \
        X.resolve(contract, "zone", "back forty") == "Z-B40"
    gate(29, "NLP entities and metrics resolve; unknown ids rejected",
         reject and ok_ids and len(contract["test_contracts"]) >= 10,
         len(contract["test_contracts"]))
    try:
        # REST endpoints: stable across SDK versions (serverless ships an older SDK)
        api = repo._ws.api_client
        spaces = api.do("GET", "/api/2.0/genie/spaces").get("spaces", []) or []
        hom_spaces = [sp for sp in spaces
                      if "house of minds" in str(sp.get("title", "")).lower()]
        dash_api = api.do("GET", "/api/2.0/lakeview/dashboards").get("dashboards", []) or []
        aibi = {"genie_available": True, "genie_spaces": len(spaces),
                "house_of_minds_genie_spaces": len(hom_spaces),
                "aibi_dashboards": len(dash_api)}
    except Exception as e:  # feature unavailable: record, do not claim
        aibi = {"error": repr(e)[:200]}
    doc = (docs / "DASHBOARD_DATA_CONTRACT.md").read_text()
    gate(30, "native AI/BI feasibility documented without unsupported claims",
         "error" not in aibi and "not configured" in doc
         and aibi.get("house_of_minds_genie_spaces") == 0, aibi)
    appx = (docs / "CLAIMS_AND_EVIDENCE_APPENDIX.md").read_text()
    gate(31, "Claims & Evidence appendix generated (4 required fields)",
         all(h in appx for h in ("Table / query", "Result", "Alternative explanation",
                                 "Limitation")) and appx.count("\n| CLM") == len(cdf),
         len(cdf))
    gate(32, "AI-use disclosure generated", (docs / "AI_USE_DISCLOSURE.md").exists()
         and "RULE_BASED" in (docs / "AI_USE_DISCLOSURE.md").read_text(), "")
    gate(33, "reproducibility guide generated", (docs / "REPRODUCIBILITY_GUIDE.md").exists(),
         "")
    gate(34, "<=400-word write-up draft", 0 < summary_words <= 400, summary_words)
    rd = (docs / "FINAL_SUBMISSION_READINESS.md").read_text()
    gate(35, "2-minute video storyboard prepared", "Video storyboard" in rd, "")
    reqs = re.findall(r"^\| (.+?) \| (READY|PARTIALLY READY|BLOCKED|FINAL DASHBOARD PHASE) \|",
                      rd, re.M)
    gate(36, "submission requirements audited", len(reqs) == 8,
         {a: b for a, b in reqs})
    after = {t: int(repo.scalar(f"SELECT count(*) FROM {t}")) for t in before}
    gate(37, "prior-phase records unchanged", after == before, len(after))
    dups = {t: int(repo.scalar(f"SELECT count(*) - count(DISTINCT {key}) FROM {t}"))
            for t, key in [("decision_passports", "passport_id"),
                           ("claims_evidence_registry", "claim_id"),
                           ("evidence_dependency_edges", "edge_id"),
                           ("evidence_dependency_nodes", "node_id")]}
    gate(38, "idempotent reruns (no duplicate logical records)", not any(dups.values()), dups)
    q = repo.query_df("""SELECT p.investment_id, count(c.claim_id) n
                         FROM decision_passports p LEFT JOIN claims_evidence_registry c
                           ON c.decision = p.investment_id GROUP BY 1""")
    gate(39, "Vault outputs queryable in Databricks", len(q) > 0, len(q))
    blockers = rd.split("## Blockers")[1].split("##")[0].count("\n- ") if "## Blockers" in rd \
        else 0
    st = dict(reqs)
    gate(40, "readiness report identifies blockers",
         blockers >= 1 and st.get("Public interactive dashboard") != "READY"
         and st.get("Video walkthrough (<=2 min)") != "READY", {"blockers": blockers})
    repo.write_table("step6_validation_summary", pa.Table.from_pylist(gates))
    summary = {"vault_run_id": vault_run, "snapshot": snapshot,
               "runtime_s": round(time.time() - t0, 1), "passports": len(passports),
               "claims": len(claims), "nodes": len(nodes), "edges": len(edges),
               "impacts": len(impacts),
               "gates": {x: sum(g_["status"] == x for g_ in gates)
                         for x in ("PASS", "FAIL", "BLOCKED")},
               "failed": [g_["gate"] for g_ in gates if g_["status"] != "PASS"],
               "export_dir": str(exp_dir), "summary_words": summary_words}
    (out_root / "reports").mkdir(parents=True, exist_ok=True)
    (out_root / "reports" / "step6_summary.json").write_text(json.dumps(summary, indent=1,
                                                                        default=str))
    print(json.dumps(summary, indent=1, default=str))
    return 1 if summary["failed"] else 0


# ------------------------------------------------------------------------- doc writers
def _cell(x: Any, n: int = 220) -> str:
    return str(x).replace("|", "/").replace("\n", " ")[:n]


def write_appendix(path: Path, claims: list[dict[str, Any]]) -> None:
    out = ["# Claims & Evidence appendix", "",
           "Generated from `claims_evidence_registry` by `scripts/run_step6.py`. Do not edit "
           "by hand. Format required by Dashboard Royale: **Table / query → Result → "
           "Alternative explanation → Limitation**. Classifications: "
           + ", ".join(B.STATUS) + ". Modeled values are not realised profit.", ""]
    by: dict[str, list[dict[str, Any]]] = {}
    for c in claims:
        by.setdefault(c["category"], []).append(c)
    for cat, rows in by.items():
        out += [f"## {cat.replace('_', ' ').title()}", "",
                "| Claim | Statement | Table / query | Result | Alternative explanation | "
                "Limitation | Class | Status |", "|---|---|---|---|---|---|---|---|"]
        for c in rows:
            stmt = _cell(c["claim_text"], 260)
            if c["original_statement"]:
                stmt = f"~~{_cell(c['original_statement'], 200)}~~ RETRACTED; correction: " \
                       f"{_cell(c['contradicting_evidence'], 200)}"
            out.append(f"| {c['claim_id']} | {stmt} | {_cell(c['source_table'], 80)}; "
                       f"`{_cell(c['query_ref'], 80)}` | {_cell(c['result'], 200)} | "
                       f"{_cell(c['alternative_explanation'])} | {_cell(c['limitation'])} | "
                       f"{c['evidence_classification']} | {c['verification_status']} |")
        out.append("")
    path.write_text("\n".join(out) + "\n")


def write_contract_doc(path: Path, manifest: list[dict[str, Any]],
                       contract: dict[str, Any]) -> None:
    out = ["# Dashboard data contract (Step 7 input)", "",
           f"Snapshot `{contract['snapshot_id']}`. Generated by `scripts/run_step6.py`. "
           "Databricks is the analytical authority: the frontend must not recompute "
           "optimiser results, reconciliations or verification.", "",
           "## Serving datasets (`workspace.house_of_minds`, also in "
           "`exports/public_snapshot_*`)", "",
           "| Dataset | Row grain | Key | Rows | Filters | Validation |",
           "|---|---|---|---:|---|---|"]
    for m in manifest:
        out.append(f"| `{m['dataset']}` | {m['row_grain']} | `{m['primary_key']}` | "
                   f"{m['rows']} | {m['filters']} | {m['validation_status']} |")
    out += ["", "Null policy: null means unknown or not applicable, never zero. Units: USD "
            "unless stated; modeled values are labelled as such.", "",
            "## Shared decision context (keys that link views)", "",
            "| Context | Key | Joins |", "|---|---|---|",
            "| period | `gaming_date` / `period` | dash_model_evaluation, dash_executive_kpis |",
            "| zone | `zone_id` | dash_machine_intelligence |",
            "| machine | `machine_id` | dash_machine_intelligence, passports.target_entity |",
            "| portfolio | `portfolio_id` | dash_investment_portfolios, "
            "dash_decision_passports |",
            "| scenario | `scenario_id` | dash_scenario_surface |",
            "| evidence | `claim_id` / `evidence_ids` | dash_evidence_validation, passports |",
            "| council event | `event_id`, `claim_id` | dash_council_activity |",
            "| model evaluation | `evaluation_run_id` | dash_model_evaluation, passports |",
            "| snapshot | `snapshot_id` | every dataset |", "",
            "## Ask the House semantic contract", "",
            f"`semantic/ask_the_house_contract.json` ({contract['contract_version']}): "
            f"{sum(len(v) for v in contract['entities'].values())} entity ids, "
            f"{len(contract['synonyms'])} synonyms, {len(contract['intents'])} intents, "
            f"{len(contract['test_contracts'])} grounded Q&A test contracts. Rules: "
            + "; ".join(contract["rules"]) + ".", "",
            "## Native Databricks AI/BI", "",
            "Serving views from Step 5 (`v_model_accuracy`, `v_decision_impact`, "
            "`v_council_ablation`, `v_portfolio_robustness`) plus the tables above can back "
            "an AI/BI dashboard. Genie is available in the workspace but **not configured** "
            "for House of Minds; no Genie answer has been verified."]
    path.write_text("\n".join(out) + "\n")


def write_repro(path: Path, repro: list[dict[str, Any]]) -> None:
    out = ["# Reproducibility guide", "", "Generated from `reproducibility_manifest`.", "",
           "## Re-run everything", "", "```sh",
           "scripts/setup.sh && scripts/fetch_data.sh",
           "uv run python scripts/run_step1.py                       # local foundation",
           "uv run python scripts/run_step1.py --backend databricks  # bronze + Step 2",
           "databricks bundle deploy -t dev",
           "databricks bundle run step2_pipeline -t dev",
           "databricks bundle run step3_decision_engine -t dev",
           "databricks bundle run step4_whisper_council -t dev",
           "uv run python scripts/run_step5.py   # writes the local forecast reference",
           "databricks bundle run step5_proving_grounds -t dev",
           "databricks bundle run step6_evidence_vault -t dev", "```", "",
           "## Manifest", "", "| Item | Value | Note |", "|---|---|---|"]
    for r in repro:
        out.append(f"| {r['item']} | {_cell(r['value'], 160)} | {_cell(r['note'], 100)} |")
    out += ["", "Known limitation: Holt-Winters metrics differ across SciPy/NumPy versions "
            "(local 5,836 vs Databricks 5,552 MAE); all decisions agree (Step 5 gate 42)."]
    path.write_text("\n".join(out) + "\n")


def write_ai(path: Path, ai: list[dict[str, Any]]) -> None:
    out = ["# AI-use disclosure", "",
           "**Short version (for submission):** We used Claude Code (Anthropic) as a coding "
           "assistant to write, run and test the code, SQL and documentation, under human "
           "direction. The analytics use no LLMs: forecasting is a statsmodels Holt-Winters "
           "model, optimisation is an exact MILP, and the six council agents are RULE_BASED "
           "deterministic analyses with a deterministic verifier. No LLM calls were made by "
           "the product (0 tokens, $0). The Ask the House interface is not yet built.", "",
           "## Detailed record (from `ai_usage_audit`)", "",
           "| Area | Implementation | Evidence | LLM used | Status |", "|---|---|---|---|---|"]
    for r in ai:
        out.append(f"| {r['area']} | {_cell(r['implementation'], 260)} | "
                   f"{_cell(r['evidence'], 120)} | {r['llm_used']} | {r['status']} |")
    path.write_text("\n".join(out) + "\n")


def write_readiness(path: Path, T: dict[str, pd.DataFrame], dash: dict[str, pd.DataFrame],
                    claims: list[dict[str, Any]], missing5: list[str]) -> int:
    k = dash["dash_executive_kpis"].set_index("kpi").value
    fc = T["forecast_baseline_comparison"].set_index("subset").loc["all"]
    summary = (
        "THE HOUSE OF MINDS turns the Gilded Ace's six months of data into an auditable "
        "$100,000 decision. Every figure reconciles: house win equals coin-in minus payout "
        f"on all machine-days (14/14 checks; ${k['house_win_usd']:,.0f} house win on "
        f"${k['coin_in_usd']:,.0f} coin-in). The manager's bottom-10 list mixes four "
        "problems: nine sit in Back Forty, the weakest zone; most run low-edge games; two "
        "were new; and M-1158 pays out far more often than its game math allows (hit-rate "
        "z = 124). It needs an inspection, not a replacement. A walkway closure cut Back "
        "Forty demand by about 31%, and the comp points price halved on May 1. "
        "An exact optimiser over the official catalog recommends two promotion weekends "
        f"(${k['evidence_portfolio_cost']:,.0f}, modeled net "
        f"${k['evidence_portfolio_modeled_net']:,.0f}) and keeping $70,000. A conditional "
        f"plan adds the inspection and two machine moves (${k['conditional_portfolio_cost']:,.0f},"
        f" ${k['conditional_portfolio_modeled_net']:,.0f}), but those effects are "
        "unmeasured. Our Decision-Reversal Engine shows when the choice flips: promotions "
        "need $5,281/day of extra theo, and the weaker past promotion measured $5,016 under "
        "a symmetric baseline. A Holt-Winters forecast beat a weekday-mean baseline on an "
        f"untouched May-June holdout (MAE ${fc.candidate_mae:,.0f} vs "
        f"${fc.baseline_mae:,.0f}). Used as a past-only counterfactual, it puts that "
        "promotion above break-even, so the decision is defensible but its causal basis is "
        "unproven (two events, no control). Six rule-based specialists and a Whisper "
        "Network challenged every assumption. Gossip retracted a false causal claim but did "
        "not change the portfolio. Each claim traces to a table, query, alternative "
        "explanation and limitation, and each action has a measurement plan with a stop "
        "rule.")
    words = len(summary.split())
    status = [
        ("Public interactive dashboard", "FINAL DASHBOARD PHASE",
         "data contracts + exports ready (Step 7)"),
        ("Video walkthrough (<=2 min)", "PARTIALLY READY", "storyboard below; not recorded"),
        ("Written summary (<=400 words)", "READY", f"draft below ({words} words)"),
        ("ML/time-series vs baseline on holdout, informing a decision",
         "READY" if not missing5 else "BLOCKED",
         "Holt-Winters vs weekday mean, May-Jun holdout, linked to A08"),
        ("All code and transformations", "READY", "repo + REPRODUCIBILITY_GUIDE.md (no git "
         "commits yet; must be pushed/published before submission)"),
        ("Up to 3 priced action types", "READY", "A-PROMO (evidence); + A-INSPECT, "
         "A-MOVE-MACHINE (conditional); costs, effects, uncertainty, measurement"),
        ("AI-use disclosure", "READY", "AI_USE_DISCLOSURE.md"),
        ("Claims & Evidence appendix", "READY", f"{len(claims)} claims"),
    ]
    out = ["# Final submission readiness", "", "| Requirement | Status | Note |",
           "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in status]
    out += ["", "## Blockers", "",
            "- Public dashboard and recorded video: Step 7.",
            "- Repository has no commits: code must be committed and published (needs your "
            "approval).",
            "- Causal promotion uplift, inspection fix probability and move transfer remain "
            "unmeasured (planning assumptions).", "",
            f"## Written summary draft ({words} words)", "", summary, "",
            "## Video storyboard (2:00)", "",
            "| Time | Screen | Narration (evidence) |", "|---|---|---|",
            "| 0:00-0:15 | Command Center KPIs | Data reconciles (CLM-REC-R01, R03) |",
            "| 0:15-0:40 | Machine Intelligence | Bottom 10 = four problems; M-1158 leak "
            "(CLM-EV-1C684B792E7B) |",
            "| 0:40-1:05 | $100K Verdict | 2 promotions, $70k kept; conditional plan "
            "(CLM-PF-*) |",
            "| 1:05-1:25 | Parallel Universes | $5,281 vs $5,016 reversal; forecast "
            "counterfactual (CLM-FORECAST-DECISION) |",
            "| 1:25-1:45 | Council Chamber / Whisper Network | Statistician challenge; "
            "retraction; gossip did not change decision (CLM-WHISPER-EVAL) |",
            "| 1:45-2:00 | Evidence Observatory | Every claim traceable; measurement plans "
            "and stop rules |"]
    path.write_text("\n".join(out) + "\n")
    return words


if __name__ == "__main__":
    _rc = main()
    if _rc:
        raise SystemExit(_rc)
