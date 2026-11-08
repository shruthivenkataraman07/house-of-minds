"""Step 3: evidence-constrained $100K optimisation, decision reversals, scenarios, regret.

Usage:
  uv run python scripts/run_step3.py                       # local DuckDB
  uv run python scripts/run_step3.py --backend databricks  # reads/writes workspace.house_of_minds

Reads Step 1/2 data only; writes nine Step 3 tables (overwritten per run, never Step 2's).
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
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
from optimization import decision_analysis as D  # noqa: E402
from optimization.action_catalog import (  # noqa: E402
    BUDGET_CENTS,
    ActionCatalog,
    SelectedAction,
    price_selection,
)
from optimization.investment_model import (  # noqa: E402
    ASSUMPTION_REQUIRED,
    NOT_IDENTIFIABLE,
    build_model,
    economics,
    effective_days,
    promo_weekends,
)
from optimization.portfolio import (  # noqa: E402
    MODE_CONDITIONAL,
    MODE_EVIDENCE,
    Portfolio,
    optimise,
    verify,
)

STEP2_TABLES = {"contract_machine_performance": 310, "contract_demand_day": 181,
                "contract_downtime_month": 126, "contract_guest_month": 18,
                "contract_comp_day": 181, "contract_intervention_options": 13,
                "reconciliation_results": 14, "machine_comparison": 310,
                "evidence_ledger": 31, "validation_summary": 6}
# Inputs computed in Step 3 directly from official tables (no Step 2 evidence record)
STEP3_SOURCES = {"A08_promo_excess_theo_per_day": "property_day,calendar_day,events"}
CANDIDATE_STATUSES = {"EVIDENCE_ESTIMATE", "EVIDENCE_UPPER_BOUND", ASSUMPTION_REQUIRED,
                      NOT_IDENTIFIABLE, "NEGATIVE_AT_BEST_CASE", "INELIGIBLE", "BLOCKED"}


def code_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((ROOT / "optimization").glob("*.py")) + [_SCRIPT]:
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def result_hash(ps: list[Portfolio]) -> str:
    payload = [[p.mode, sorted(p.allocation.items()), round(p.net_benefit, 2)] for p in ps]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:16]


def open_repo(backend: str) -> Any:
    s = get_settings()
    if backend == "databricks":
        from backend.repositories.databricks_repo import DatabricksRepository
        return DatabricksRepository(s.databricks_warehouse_id or "", s.databricks_catalog,
                                    s.databricks_schema, s.databricks_profile)
    from pipelines.ingestion.loader import open_local_repository
    return open_local_repository(s)


def load_ledger(repo: Any, backend: str) -> pd.DataFrame:
    if backend == "databricks":
        df = repo.query_df("SELECT * FROM evidence_ledger")
        df["source_tables"] = df.source_tables.map(json.loads)
        return df
    rows = [json.loads(x) for x in
            (ROOT / "data/processed/evidence_ledger.jsonl").read_text().splitlines()]
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["duckdb", "databricks"], default="duckdb")
    ap.add_argument("--warehouse-id")
    ap.add_argument("--catalog")
    ap.add_argument("--schema")
    ap.add_argument("--output-dir")
    ap.add_argument("--job-run-id", help="Databricks {{job.run_id}} for provenance")
    args = ap.parse_args(argv)
    if args.job_run_id:
        os.environ["DATABRICKS_JOB_RUN_ID"] = args.job_run_id
    for flag, env in [("warehouse_id", "DATABRICKS_WAREHOUSE_ID"),
                      ("catalog", "DATABRICKS_CATALOG"), ("schema", "DATABRICKS_SCHEMA"),
                      ("output_dir", "HOM_OUTPUT_DIR")]:
        if getattr(args, flag):
            os.environ[env] = getattr(args, flag)
    get_settings.cache_clear()
    t0 = time.time()
    out_root = Path(os.environ.get("HOM_OUTPUT_DIR", str(ROOT)))
    out_dir = out_root / "data" / "processed" / "step3" / args.backend
    out_dir.mkdir(parents=True, exist_ok=True)
    rep_dir = out_root / "reports" / "step3"
    rep_dir.mkdir(parents=True, exist_ok=True)

    repo = open_repo(args.backend)
    manifest = json.loads((ROOT / "reports" / "dataset_manifest.json").read_text())
    existing = set(repo.list_tables())
    step2_before = {t: int(repo.scalar(f"SELECT count(*) FROM {t}"))
                    for t in STEP2_TABLES if t in existing}
    ledger = load_ledger(repo, args.backend)
    ledger_ids = set(ledger.evidence_id)

    catalog = ActionCatalog.load(repo)
    model = build_model(repo, catalog)
    created = datetime.now(UTC)
    run_id = (f"S3-{created.strftime('%Y%m%dT%H%M%SZ')}-{model.fingerprint()}"
              + (f"-JOB{os.environ['DATABRICKS_JOB_RUN_ID']}"
                 if os.environ.get("DATABRICKS_JOB_RUN_ID") else ""))

    # ---- optimisation ------------------------------------------------------------------
    base_c = optimise(model, MODE_CONDITIONAL)
    base_e = optimise(model, MODE_EVIDENCE)
    runner_ups: list[tuple[str, Portfolio]] = []
    for t in sorted({next(c.action_type for c in model.candidates if c.candidate_id == k)
                     for k in base_c.allocation}):
        m2 = model.__class__(**{**model.__dict__,
                                "candidates": [c for c in model.candidates
                                               if c.action_type != t]})
        runner_ups.append((f"runner_up_without_{t}", optimise(m2, MODE_CONDITIONAL)))
    reversals = D.decision_reversals(model)
    scen = D.run_scenarios(model, base_c)
    regret = D.regret_summary(model, base_c, scen)
    inval = [D.invalidation_test(model, "A08_promo_excess_theo_per_day", MODE_EVIDENCE),
             D.invalidation_test(model, "A01_inspect_fix_probability", MODE_CONDITIONAL),
             D.invalidation_test(model, "A09_move_location_transfer", MODE_CONDITIONAL)]
    runtime = time.time() - t0
    rhash = result_hash([base_e, base_c])
    rerun_hash = result_hash([optimise(model, MODE_EVIDENCE), optimise(model, MODE_CONDITIONAL)])

    # ---- tables --------------------------------------------------------------------------
    econ = {c.candidate_id: economics(model, c) for c in model.candidates}
    cand_rows = []
    for c in model.candidates:
        e = econ[c.candidate_id]
        act = catalog.actions[c.action_type]
        # worst / best case over every low/high combination of its assumptions
        outcomes = []
        for combo in itertools.product(*[(model.assumptions[k].low, model.assumptions[k].high)
                                         for k in c.assumptions]):
            mm = model
            for k, v in zip(c.assumptions, combo, strict=True):
                mm = mm.with_assumption(k, v)
            n = economics(mm, c).net_per_unit
            if n is not None:
                outcomes.append(n)
        lows, highs = [min(outcomes, default=None)], [max(outcomes, default=None)]
        cand_rows.append({
            "run_id": run_id, "investment_id": c.candidate_id, "action_type": c.action_type,
            "target_entity": c.target_entity, "unit_cost": e.unit_cost,
            "max_quantity": e.max_quantity, "lead_time_days": act.lead_days,
            "earliest_start_date": str(act.effective_from),
            "effective_days_within_horizon": e.effective_days, "eligible": c.eligible,
            "eligibility_reason": c.eligibility_reason,
            "dependencies": ",".join(c.assumptions),
            "incompatibility_group": act.incompatibility_group,
            "observed_financial_signal": c.observed_signal,
            "gross_theo_gain": e.gross_theo_gain, "contribution_gain": e.contribution_gain,
            "avoided_costs": e.avoided_costs, "downtime_cost": e.downtime_cost,
            "benefit_base": e.net_per_unit, "benefit_low": lows[0], "benefit_high": highs[0],
            "benefit_status": e.status, "causal_status": c.causal_status,
            "evidence_ids": ",".join(c.evidence_ids), "notes": c.notes})
    asm_rows = [{"run_id": run_id, **a.as_row()} for a in model.assumptions.values()]

    portfolios = [("baseline", base_e), ("baseline", base_c)] + runner_ups
    run_rows, alloc_rows = [], []
    for role, p in portfolios:
        run_rows.append({
            "run_id": run_id, "role": role, "mode": p.mode, "portfolio_id": p.portfolio_id,
            "portfolio": p.signature, "total_cost": p.total_cost,
            "unspent_budget": BUDGET_CENTS / 100 - p.total_cost, "net_benefit": p.net_benefit,
            "objective": "max incremental net contribution over 2025-07-01..2025-07-30; "
                         "tie-break min cost, then candidate id",
            "solver": "SciPy milp (HiGHS), mip_rel_gap=0, lexicographic",
            "input_fingerprint": model.fingerprint(), "result_hash": rhash,
            "dataset_fingerprint": manifest["fingerprint"], "code_hash": code_hash(),
            "runtime_seconds": round(runtime, 2), "created_at_utc": created.isoformat(),
            "verification": "; ".join(verify(model, p)) or "OK"})
        for k, q in sorted(p.allocation.items()):
            e = econ[k]
            alloc_rows.append({"run_id": run_id, "role": role, "mode": p.mode,
                               "portfolio_id": p.portfolio_id, "investment_id": k,
                               "quantity": q, "unit_cost": e.unit_cost,
                               "line_cost": e.unit_cost * q, "net_per_unit": e.net_per_unit,
                               "line_net": (e.net_per_unit or 0) * q,
                               "benefit_status": e.status})
    scen_rows = [{"run_id": run_id, **{k: v for k, v in r.items() if k != "_allocation"}}
                 for r in scen]
    rev_rows = [{"run_id": run_id, **r.__dict__} for r in reversals]
    reg_rows = [{"run_id": run_id, **{k: (json.dumps(v) if isinstance(v, (list, dict))
                                          else v) for k, v in regret.items()}}]

    # Evidence passport: decision -> candidate -> assumption -> Step 2 evidence record
    ev_by_id = ledger.set_index("evidence_id")
    links = []
    for role, p in portfolios:
        for k in sorted(p.allocation) or ["HOLD"]:
            c = next((x for x in model.candidates if x.candidate_id == k), None)
            keys = c.assumptions if c else []
            for akey in keys or [None]:
                a = model.assumptions[akey] if akey else None
                eids = (a.evidence_ids if a else []) or (c.evidence_ids if c else []) or [None]
                for eid in eids:
                    known = eid in ledger_ids if eid else False
                    links.append({
                        "run_id": run_id, "scenario_id": "baseline", "role": role,
                        "mode": p.mode, "portfolio_id": p.portfolio_id, "investment_id": k,
                        "assumption_id": akey, "assumption_value": a.value if a else None,
                        "assumption_unit": a.unit if a else None,
                        "assumption_status": a.status if a else None,
                        "causal_status": a.causal_status if a else None,
                        "evidence_id": eid, "evidence_resolved": known,
                        "provenance_type": "step2_evidence_record" if known else (
                            "step3_source_query" if a else "none"),
                        "evidence_validation_state": ev_by_id.loc[eid, "validation_state"]
                        if known else None,
                        "evidence_source_tables": ",".join(ev_by_id.loc[eid, "source_tables"])
                        if known else (STEP3_SOURCES.get(akey, a.source) if a else None),
                        "dataset_fingerprint": manifest["fingerprint"],
                        "dataset_version": manifest["dataset_version"],
                        "code_hash": code_hash(),
                        "claim_id": "CLM-" + hashlib.sha256(
                            f"{p.portfolio_id}|{k}".encode()).hexdigest()[:10].upper(),
                        "challenge_id": "CHL-" + hashlib.sha256(
                            f"{k}|{akey}|{eid}".encode()).hexdigest()[:10].upper()})

    # ---- acceptance tests -----------------------------------------------------------------
    checks: list[dict[str, Any]] = []

    def check(n: int, name: str, ok: bool | None, detail: Any) -> None:
        checks.append({"run_id": run_id, "test_no": n, "test": name,
                       "status": "BLOCKED" if ok is None else ("PASS" if ok else "FAIL"),
                       "detail": json.dumps(detail, default=str)[:900]})

    all_ps = [p for _, p in portfolios]
    scen_models = {s["id"]: D.scenario_model(model, s) for s in D.SCENARIOS}
    check(1, "spend never exceeds $100,000",
          all(p.total_cost <= 100000 for p in all_ps)
          and all(r["optimal_cost"] <= 100000 for r in scen),
          {"max_cost": max([p.total_cost for p in all_ps] + [r["optimal_cost"] for r in scen])})
    qty_ok = all(q <= econ[k].max_quantity for p in all_ps for k, q in p.allocation.items())
    check(2, "quantity restrictions respected", qty_ok, "per-candidate and per-type limits")
    vio = [verify(model, p) for p in all_ps]
    check(3, "incompatibilities respected (catalog validator)", all(not v for v in vio), vio)
    lease = price_selection(catalog, [SelectedAction(action_type_id="A-REPLACE-LEASE",
                                                     quantity=1)]).total_usd
    timing_ok = (lease == 3380.0 and promo_weekends(14) == 2
                 and all(econ[c.candidate_id].effective_days
                         == effective_days(catalog.actions[c.action_type].lead_days)
                         for c in model.candidates))
    check(4, "lead times and effective benefit days", timing_ok,
          {"lease_example_usd": lease, "promo_weekends": promo_weekends(14)})
    neg = [k for p in all_ps for k in p.allocation if (econ[k].net_per_unit or 0) <= 0]
    check(5, "negative-net investments not forced", not neg, neg)
    w = econ["INV-WAYFIND-B40"]
    unit_ok = abs(w.gross_theo_gain - model.a("A03_wayfinding_net_uplift")
                  * model.facts["b40_theo_per_day_excl_movers"] * w.effective_days) < 0.01
    check(6, "consistent units and horizon (USD over effective days)", unit_ok,
          "wayfinding gross = uplift x USD/day x effective days")
    movers = [c for c in model.candidates if c.action_type == "A-MOVE-MACHINE"]
    dbl_ok = (all("M-1158" not in c.machines for c in movers)
              and model.facts["b40_theo_per_day_excl_movers"] < model.facts["b40_theo_per_day"])
    check(7, "no double counting of overlapping benefits", dbl_ok,
          "M-1158 excluded from moves; wayfinding base excludes move candidates")
    sel_e = [k for k in base_e.allocation if econ[k].status not in
             {"EVIDENCE_ESTIMATE", "EVIDENCE_UPPER_BOUND"}]
    never = [k for p in all_ps for k in p.allocation
             if econ[k].status in {NOT_IDENTIFIABLE, "INELIGIBLE", "NEGATIVE_AT_BEST_CASE"}]
    check(8, "missing assumptions never become facts", not sel_e and not never,
          {"assumption_based_in_evidence_portfolio": sel_e, "unidentifiable_selected": never})
    check(9, "identical-input reruns identical", rhash == rerun_hash, rhash)
    s10 = scen_models["S10_inspection_fails"]
    insp = next(c for c in model.candidates if c.candidate_id == "INV-INSPECT-M1158")
    promo = next(c for c in model.candidates if c.candidate_id == "INV-PROMO")
    check(10, "scenario changes propagate", economics(s10, insp).net_per_unit
          < econ[insp.candidate_id].net_per_unit, "S10 lowers inspection net")
    check(11, "unaffected economics unchanged", economics(s10, promo).net_per_unit
          == econ[promo.candidate_id].net_per_unit, "S10 leaves promotion net identical")
    rev_ok = True
    for r in reversals:
        if r.reversal_found:
            lo = optimise(model.with_assumption(r.assumption_id, r.interval_low), r.mode)
            hi = optimise(model.with_assumption(r.assumption_id, r.interval_high), r.mode)
            rev_ok &= (lo.signature == r.original_portfolio
                       and hi.signature == r.replacement_portfolio)
    check(12, "every reversal re-verified by reoptimisation", rev_ok,
          {"reversals": sum(r.reversal_found for r in reversals)})
    synth = D.scan_reversals(0, 1, lambda v: ("B" if 100 * v > 60 else "A", None))
    check(13, "synthetic known-reversal case",
          len(synth) == 1 and synth[0]["interval_low"] <= 0.6 <= synth[0]["interval_high"],
          "known boundary 0.6 (full known-optimum suite: tests/unit/test_step3_optimizer.py)")
    check(14, "regret non-negative within tolerance", min(r["regret"] for r in scen) >= -1e-6,
          {"min_regret": min(r["regret"] for r in scen)})
    check(15, "baseline re-evaluated in every scenario",
          len(scen) == len(D.SCENARIOS)
          and all(r["baseline_net_under_scenario"] is not None for r in scen), len(scen))
    used = {e for c in model.candidates for e in c.evidence_ids} | {
        e for a in model.assumptions.values() for e in a.evidence_ids}
    no_prov = [x for x in links if x["provenance_type"] == "none" and x["investment_id"] != "HOLD"]
    check(16, "evidence references resolve (Step 2 record or named source query)",
          used <= ledger_ids and not no_prov,
          {"unresolved_ids": sorted(used - ledger_ids), "links_without_provenance": len(no_prov),
           "provenance_types": sorted({x["provenance_type"] for x in links})})
    check(17, "invalidated assumptions block dependent decisions",
          all(i["status"] == "PASS" for i in inval), inval)
    status_ok = (all(r["benefit_status"] in CANDIDATE_STATUSES for r in cand_rows)
                 and all(a["status"] and a["source"] for a in asm_rows))
    check(19, "outputs genuine and correctly classified", status_ok,
          {"statuses": sorted({r["benefit_status"] for r in cand_rows})})

    tables = {"investment_candidates": cand_rows, "intervention_assumptions": asm_rows,
              "optimization_runs": run_rows, "portfolio_allocations": alloc_rows,
              "scenario_results": scen_rows, "decision_reversals": rev_rows,
              "portfolio_regret": reg_rows, "decision_evidence_links": links}
    for name, rows in tables.items():
        df = pd.DataFrame(rows)
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
        repo.write_table(name, pa.Table.from_pandas(df, preserve_index=False))

    step2_after = {t: int(repo.scalar(f"SELECT count(*) FROM {t}")) for t in step2_before}
    src_ok = all(int(repo.scalar(f"SELECT count(*) FROM {t['table']}")) == t["rows"]
                 for t in manifest["tables"] if t["status"] != "missing")
    check(18, "Step 1 and Step 2 data unchanged",
          src_ok and step2_after == step2_before
          and (args.backend != "databricks" or step2_after == {
              k: v for k, v in STEP2_TABLES.items()}),
          {"step2_counts": step2_after, "sources_match_manifest": src_ok})
    q = repo.query_df("""SELECT r.mode, r.portfolio, r.total_cost, r.net_benefit,
                            count(a.investment_id) lines
                         FROM optimization_runs r LEFT JOIN portfolio_allocations a
                           ON a.portfolio_id = r.portfolio_id AND a.run_id = r.run_id
                          AND a.role = r.role
                         WHERE r.role = 'baseline' GROUP BY 1, 2, 3, 4""")
    check(20, "portfolio results queryable via SQL", len(q) == 2, q.to_dict("records"))
    checks.sort(key=lambda c: c["test_no"])
    pd.DataFrame(checks).to_parquet(out_dir / "optimizer_validation_summary.parquet",
                                    index=False)
    repo.write_table("optimizer_validation_summary", pa.Table.from_pylist(checks))

    summary = {"run_id": run_id, "backend": args.backend, "runtime_seconds": round(runtime, 1),
               "evidence_portfolio": [base_e.signature, base_e.total_cost, base_e.net_benefit],
               "conditional_portfolio": [base_c.signature, base_c.total_cost,
                                         base_c.net_benefit],
               "result_hash": rhash,
               "tests": {c["status"]: sum(1 for x in checks if x["status"] == c["status"])
                         for c in checks},
               "failed": [c["test"] for c in checks if c["status"] != "PASS"],
               "regret": {k: v for k, v in regret.items() if k != "candidate_portfolios"},
               "reversals": [r.__dict__ for r in reversals if r.reversal_found],
               "invalidation": inval}
    (rep_dir / f"step3_summary_{args.backend}.json").write_text(
        json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: summary[k] for k in ("run_id", "evidence_portfolio",
                                              "conditional_portfolio", "tests", "failed")},
                     indent=1, default=str))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    _rc = main()
    if _rc:  # serverless treats any SystemExit (even 0) as failure: raise only on error
        raise SystemExit(_rc)
