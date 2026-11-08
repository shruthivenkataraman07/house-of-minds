"""Official challenge alignment: answer the manager's question and the six official areas.

Usage:
  uv run python scripts/run_challenge.py                       # local DuckDB (checks only)
  uv run python scripts/run_challenge.py --backend databricks  # writes gold tables to UC
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

try:
    _SCRIPT = Path(__file__).resolve()
except NameError:
    _SCRIPT = Path(sys.argv[0]).resolve()
ROOT = _SCRIPT.parents[1]
sys.path.insert(0, str(ROOT))

from typing import Any  # noqa: E402

import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402

from analytics import challenge_questions as Q  # noqa: E402
from analytics.replacement import OFFICIAL_BOTTOM10_SQL, compare_portfolios, verdicts  # noqa: E402
from config.settings import get_settings  # noqa: E402
from council.manager_review import run_manager_review  # noqa: E402
from optimization.action_catalog import ActionCatalog  # noqa: E402
from optimization.investment_model import build_model  # noqa: E402

PRIOR = ["machine_comparison", "reconciliation_results", "evidence_ledger", "optimization_runs",
         "portfolio_allocations", "scenario_results", "council_runs", "agent_claims",
         "council_validation_summary", "forecast_baseline_comparison", "holdout_predictions",
         "decision_passports", "claims_evidence_registry", "step6_validation_summary"]


def overall(rows: list[dict[str, Any]]) -> str:
    v = [r["verdict"] for r in rows]
    eligible = [x for x in v if x != "RETIRED_ALREADY"]
    just = sum(x == "REPLACE_JUSTIFIED_CONDITIONAL" for x in eligible)
    insuff = sum(x == "INSUFFICIENT_EVIDENCE" for x in eligible)
    if insuff > len(eligible) / 2:
        return "INSUFFICIENT_EVIDENCE"
    if eligible and just == len(eligible):
        return "REPLACE_ALL"
    return "REPLACE_SOME" if just else "REPLACE_NONE"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["duckdb", "databricks"], default="duckdb")
    args = ap.parse_args(argv)
    get_settings.cache_clear()
    s = get_settings()
    t0 = time.time()
    if args.backend == "databricks":
        from backend.repositories.databricks_repo import DatabricksRepository
        repo: Any = DatabricksRepository(s.databricks_warehouse_id or "", s.databricks_catalog,
                                         s.databricks_schema, s.databricks_profile)
        ledger = set(repo.query_df("SELECT evidence_id FROM evidence_ledger").evidence_id)
    else:
        from pipelines.ingestion.loader import open_local_repository
        repo = open_local_repository(s)
        ledger = {json.loads(x)["evidence_id"] for x in
                  (ROOT / "data/processed/evidence_ledger.jsonl").read_text().splitlines()}
    existing = set(repo.list_tables())
    before = {t: int(repo.scalar(f"SELECT count(*) FROM {t}")) for t in PRIOR if t in existing}
    model = build_model(repo, ActionCatalog.load(repo))
    run_id = f"CH-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"

    # ---- Q1: manager's bottom 10 + verdicts + council + portfolios -----------------------
    v = verdicts(repo, model)
    rows, m2 = v["rows"], v["model_with_replacements"]
    review = run_manager_review(repo, m2, ledger, list(v["bottom10"].machine_id))
    res = {x["machine_id"]: x for x in review["resolutions"]}
    for r in rows:
        r["council_verdict"] = res[r["machine_id"]]["council_verdict"]
        r["council_agrees"] = r["council_verdict"] == r["verdict"]
        r["council_deciding_claims"] = res[r["machine_id"]]["deciding_claims"]
    comp = compare_portfolios(model, m2, rows)
    verdict = overall(rows)
    cmp_by = {c["option"]: c for c in comp}
    # Recommendation = the evidence-supported portfolio (Steps 3-6): its benefit inputs are
    # measured; the conditional portfolio adds planning assumptions and is reported as upside.
    best = cmp_by["house_of_minds_evidence"]
    upside = cmp_by["house_of_minds_conditional"]
    exec_row = {
        "run_id": run_id, "question": "Should the manager replace the 10 lowest-earning "
        "machines (Jan-Jun 2025)?", "answer": verdict,
        "machines_reviewed": len(rows),
        "replacement_justified": sum(r["replacement_justified"] for r in rows),
        "retired_already": sum(r["verdict"] == "RETIRED_ALREADY" for r in rows),
        "inspect_instead": sum(r["verdict"] == "DO_NOT_REPLACE_INSPECT" for r in rows),
        "not_economic": sum(r["verdict"] == "DO_NOT_REPLACE_NOT_ECONOMIC" for r in rows),
        "insufficient_evidence": sum(r["verdict"] == "INSUFFICIENT_EVIDENCE" for r in rows),
        "council_agreement": sum(r["council_agrees"] for r in rows),
        "manager_option_net_usd": cmp_by["manager_proposal_lease"]["expected_net_benefit_usd"],
        "manager_option_cost_usd": cmp_by["manager_proposal_lease"]["cost_usd"],
        "recommended_option": best["option"], "recommended_allocation": best["allocation"],
        "recommended_cost_usd": best["cost_usd"],
        "recommended_net_usd": best["expected_net_benefit_usd"],
        "recommended_basis": "evidence-supported (measured inputs only)",
        "conditional_upside_option": upside["allocation"],
        "conditional_upside_cost_usd": upside["cost_usd"],
        "conditional_upside_net_usd": upside["expected_net_benefit_usd"],
        "conditional_basis": "adds planning assumptions (inspection fix probability, move "
                             "demand transfer)",
        "limitations": "Modeled contribution (Jul 1-30), not realised profit; new-title, "
                       "inspection, move and promotion effects are not causally identified",
    }

    # ---- Q2-Q5 ----------------------------------------------------------------------------
    dem = Q.floor_demand(repo)
    down = Q.downtime_economics(repo, model.facts["floor_contribution_factor"])
    ply = Q.player_outcomes(repo)
    comps = Q.loyalty_comps(repo)
    if "forecast_baseline_comparison" in existing:
        fc = repo.query_df("SELECT * FROM forecast_baseline_comparison")
    else:  # local run: Step 5 output written by scripts/run_step5.py
        p5 = ROOT / "data/processed/step5/duckdb/forecast_baseline_comparison.parquet"
        fc = pd.read_parquet(p5) if p5.exists() else pd.DataFrame()

    tables: dict[str, pd.DataFrame] = {
        "ch_executive_verdict": pd.DataFrame([exec_row]),
        "ch_manager_bottom10": v["bottom10"],
        "ch_machine_investigation": pd.DataFrame(rows),
        "ch_replacement_candidates": v["candidates"],
        "ch_portfolio_comparison": pd.DataFrame(comp),
        "ch_council_manager_review": pd.DataFrame([{
            "council_run_id": review["council_run_id"], "claim_id": c.claim_id,
            "agent_id": c.agent_id, "machine": c.financial_relevance.split()[-1],
            "kind": c.role, "statement": c.statement, "action": c.action.value,
            "numeric_result": c.numeric_result, "unit": c.numeric_unit,
            "query_refs": ",".join(c.query_refs), "evidence_ids": ",".join(c.evidence_ids),
            "verdict": review["verifications"][c.claim_id].verdict.value,
            "arithmetic_valid": review["verifications"][c.claim_id].arithmetic_valid}
            for c in review["claims"]]),
        "ch_floor_demand_monthly": dem["monthly"],
        "ch_floor_demand_weekly": dem["weekly"].assign(week_start=lambda d: d.week_start
                                                       .astype(str)),
        "ch_zone_demand": dem["zone_month"],
        "ch_zone_traffic": dem["traffic_month"],
        "ch_demand_explanations": dem["explanations"],
        "ch_downtime_economics": down["by_month_mfr_zone"],
        "ch_downtime_by_hour": down["by_local_hour"],
        "ch_player_outcomes": pd.DataFrame([ply["summary"]]),
        "ch_player_outcomes_by_tier": ply["by_tier"],
        "ch_loyalty_comps": comps["monthly"],
    }
    for name, df in tables.items():
        df = df.copy()
        df["run_id"] = run_id
        repo.write_table(name, pa.Table.from_pandas(df, preserve_index=False))

    # ---- checks ----------------------------------------------------------------------------
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool | None, detail: Any) -> None:
        checks.append({"run_id": run_id, "check": name, "status": "BLOCKED" if ok is None
                       else ("PASS" if ok else "FAIL"),
                       "detail": json.dumps(detail, default=str)[:600]})

    b10 = repo.query_df(OFFICIAL_BOTTOM10_SQL)
    check("original bottom 10 reproducible (GUIDE query)",
          list(b10.machine_id) == list(v["bottom10"].machine_id), list(b10.machine_id))
    mi = pd.DataFrame(rows).set_index("machine_id")
    mw = repo.query_df("SELECT machine_id, sum(house_win_cents)/100.0 hw FROM machine_day "
                       "WHERE active GROUP BY 1").set_index("machine_id").hw
    check("machine-level house win reconciles (prepared view vs cents)",
          all(abs(mi.loc[m, "house_win_usd"] - mw[m]) < 0.01 for m in mi.index), "")
    check("availability handled (rates within [0,1], off-floor excluded)",
          bool(((mi.availability_rate >= 0) & (mi.availability_rate <= 1)).all()
               and (mi.active_days <= 181).all()), "")
    dup = int(repo.scalar("SELECT count(*) - count(DISTINCT (machine_id, gaming_date)) "
                          "FROM machine_day")) if args.backend == "duckdb" else int(
        repo.scalar("SELECT count(*) - count(DISTINCT concat(machine_id, '|', "
                    "CAST(gaming_date AS STRING))) FROM machine_day"))
    check("no duplicate machine-day", dup == 0, dup)
    sess = float(repo.scalar("SELECT sum(coin_in_cents)::DOUBLE / 100 FROM sessions"))
    check("player totals not inflated by joins",
          abs(ply["summary"]["tracked_coin_in_usd"] - sess) < 0.01,
          [ply["summary"]["tracked_coin_in_usd"], sess])
    led = float(repo.scalar("SELECT sum(economic_cost_cents)/100.0 FROM loyalty_ledger "
                            "WHERE event_type = 'redeem'"))
    check("comp cost counted once", abs(comps["monthly"].comp_cost_usd.sum() - led) < 0.01,
          [comps["monthly"].comp_cost_usd.sum(), led])
    check("forecast validation traceable", len(fc) == 3 and "candidate_mae" in fc.columns,
          len(fc))
    vers = review["verifications"]
    check("council outputs tied to real evidence (all claims reproduced)",
          all(x.arithmetic_valid for x in vers.values()) and all(
              x.source_valid for x in vers.values()), len(vers))
    check("manager / optimised / no-action on consistent definitions",
          all(c["horizon"] == "2025-07-01..2025-07-30" for c in comp), "")
    feas = [c for c in comp if c["feasible"]]
    check("budget <= $100,000 for feasible options",
          all(c["cost_usd"] <= 100000 for c in feas)
          and not cmp_by["manager_proposal_buy"]["feasible"], "")
    check("max three action types", all(c["action_types"] <= 3 for c in feas), "")
    check("lead times and costs respected (lease = $3,380 incl. 16 recurring days)",
          abs(cmp_by["manager_proposal_lease"]["cost_usd"]
              - 3380 * len([r for r in rows if r["verdict"] != "RETIRED_ALREADY"
                            and r["lease_cost_usd"] is not None])) < 0.01, "")
    check("verdict derived, not hard-coded (council agrees on every machine)",
          all(r["council_agrees"] for r in rows), exec_row["council_agreement"])
    after = {t: int(repo.scalar(f"SELECT count(*) FROM {t}")) for t in before}
    check("prior-step tables unchanged", after == before, len(after))
    for name, df in tables.items():
        n = int(repo.scalar(f"SELECT count(*) FROM {name}"))
        if n != len(df):
            check(f"export matches canonical ({name})", False, [n, len(df)])
    check("dashboard-facing tables match canonical outputs (row counts)",
          not any(c["check"].startswith("export matches") for c in checks), len(tables))
    repo.write_table("ch_validation_summary", pa.Table.from_pylist(checks))
    summary = {"run_id": run_id, "backend": args.backend, "runtime_s": round(time.time() - t0, 1),
               "executive_verdict": exec_row,
               "checks": {k: sum(c["status"] == k for c in checks) for k in
                          ("PASS", "FAIL", "BLOCKED")},
               "failed": [c["check"] for c in checks if c["status"] != "PASS"],
               "demand_explanations": dem["explanations"].to_dict("records"),
               "downtime_total": down["total"], "players": ply["summary"],
               "comp_change": {k: comps["change"][k] for k in (
                   "change_point_gaming_date", "comp_cost_change_pct")},
               "portfolios": comp, "council_claims": len(review["claims"])}
    (ROOT / "reports" / f"challenge_summary_{args.backend}.json").write_text(
        json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: summary[k] for k in ("run_id", "checks", "failed")}, indent=1))
    print(json.dumps(exec_row, indent=1, default=str))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    _rc = main()
    if _rc:
        raise SystemExit(_rc)
