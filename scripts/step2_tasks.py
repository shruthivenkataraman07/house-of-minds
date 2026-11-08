"""Databricks job tasks (Step 2). Each task reuses existing pipeline code.

  verify_sources      volume files vs official SHA-256; bronze row counts vs manifest
                      (read-only: never reloads the 31 source tables)
  reconciliation      14 financial checks -> reconciliation_results (fails on any fail)
  machine_comparison  fair comparison -> machine_comparison (validates exposure denominators)
  data_contracts      six contract tables (schema-validated rows) -> contract_*
  evidence_summary    full evidence ledger (same ids as local) + validation_summary table

Usage: python scripts/step2_tasks.py <task> --warehouse-id ID [--catalog C --schema S]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    _SCRIPT = Path(__file__).resolve()
except NameError:  # Databricks serverless runs the file via exec() without __file__
    _SCRIPT = Path(sys.argv[0]).resolve()
ROOT = _SCRIPT.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import pyarrow as pa  # noqa: E402

TASKS = ["verify_sources", "reconciliation", "machine_comparison", "data_contracts",
         "evidence_summary"]
CONTRACT_TABLES = ["contract_machine_performance", "contract_demand_day",
                   "contract_downtime_month", "contract_guest_month", "contract_comp_day",
                   "contract_intervention_options"]


def _repo():  # type: ignore[no-untyped-def]
    from backend.repositories.databricks_repo import DatabricksRepository
    from config.settings import get_settings
    s = get_settings()
    return s, DatabricksRepository(s.databricks_warehouse_id or "", s.databricks_catalog,
                                   s.databricks_schema, s.databricks_profile)


def _manifest() -> dict:  # type: ignore[type-arg]
    return json.loads((ROOT / "reports" / "dataset_manifest.json").read_text())


def verify_sources() -> int:
    from pipelines.ingestion.databricks_bronze import verify_volume_files, volume_root
    s, repo = _repo()
    man = _manifest()
    vol = verify_volume_files(repo._ws, man, volume_root(s.databricks_catalog,
                                                         s.databricks_schema))
    bad_files = [v["table"] for v in vol if not v["verified"]]
    bad_rows = []
    for t in man["tables"]:
        if t["status"] == "missing":
            continue
        n = int(repo.scalar(f"SELECT count(*) FROM `{t['table']}`"))
        if n != t["rows"]:
            bad_rows.append((t["table"], n, t["rows"]))
    print(f"files verified {len(vol) - len(bad_files)}/{len(vol)}; row-count mismatches "
          f"{bad_rows or 'none'}")
    return 1 if bad_files or bad_rows else 0


def reconciliation() -> int:
    from pipelines.validation.reconciliation import run_all
    _, repo = _repo()
    res = run_all(repo)
    repo.write_table("reconciliation_results", pa.Table.from_pylist(
        [{**r.model_dump(), "calculated_result": json.dumps(r.calculated_result, default=str),
          "input_data": ",".join(r.input_data)} for r in res]))
    failed = [r.test_id for r in res if r.status == "fail"]
    print(f"reconciliation: {len(res) - len(failed)}/{len(res)} not failed; failed={failed}")
    return 1 if failed else 0


def machine_comparison() -> int:
    from analytics.machine_performance import compare_machines
    _, repo = _repo()
    cmp = compare_machines(repo)
    m = cmp.machines
    bad = int((m.available_hours <= 0).sum() + m.win_per_available_hour.isna().sum()
              + m.theo_per_available_hour.isna().sum())
    repo.write_table("machine_comparison", pa.Table.from_pandas(
        m.drop(columns=["install_date", "retire_date"], errors="ignore"), preserve_index=False))
    print(f"machine_comparison: {len(m)} machines; invalid exposure denominators={bad}")
    return 1 if bad or len(m) != 310 else 0


def data_contracts() -> int:
    from analytics import contracts as C
    from analytics.machine_performance import compare_machines
    from backend.schemas.contracts import CONTRACTS
    from optimization.action_catalog import ActionCatalog
    _, repo = _repo()
    tables = {"machine_performance": C.machine_performance(compare_machines(repo)),
              "intervention_planning": C.intervention_planning(ActionCatalog.load(repo))}
    for name, fn in C.BUILDERS.items():
        tables[name] = fn(repo)  # each row validated against its Pydantic schema
    for spec in CONTRACTS:
        repo.write_table(spec.output_table,
                         pa.Table.from_pandas(tables[spec.domain], preserve_index=False))
        print(f"{spec.output_table}: {len(tables[spec.domain])} rows")
    return 0


def evidence_summary() -> int:
    """Rebuild the evidence ledger with the main pipeline, then record acceptance checks."""
    import run_step1  # noqa: PLC0415  (same folder)
    rc = run_step1.main(["--backend", "databricks", "--skip-bronze", "--skip-profile"])
    s, repo = _repo()
    man = _manifest()
    checks = []

    def add(name: str, ok: bool, detail: object) -> None:
        checks.append({"check": name, "status": "PASS" if ok else "FAIL",
                       "detail": json.dumps(detail, default=str)})

    counts = {t["table"]: int(repo.scalar(f"SELECT count(*) FROM `{t['table']}`"))
              for t in man["tables"] if t["status"] != "missing"}
    add("source_counts_unchanged",
        all(counts[t["table"]] == t["rows"] for t in man["tables"] if t["table"] in counts),
        {"tables": len(counts)})
    rec = repo.query_df("SELECT test_id, status FROM reconciliation_results")
    add("no_reconciliation_failures", len(rec) == 14 and (rec.status != "fail").all(),
        rec.status.value_counts().to_dict())
    dup = {}
    for t, key in [("reconciliation_results", "test_id"), ("machine_comparison", "machine_id"),
                   ("evidence_ledger", "evidence_id"),
                   ("contract_machine_performance", "machine_id"),
                   ("contract_demand_day", "gaming_date"),
                   ("contract_intervention_options", "action_type_id")]:
        dup[t] = int(repo.scalar(f"SELECT count(*) - count(DISTINCT {key}) FROM `{t}`"))
    add("no_duplicate_output_records", not any(dup.values()), dup)
    empty = {t: int(repo.scalar(f"SELECT count(*) FROM `{t}`")) for t in CONTRACT_TABLES}
    add("contracts_populated", all(v > 0 for v in empty.values()), empty)
    den = int(repo.scalar("SELECT count(*) FROM machine_comparison WHERE available_hours <= 0 "
                          "OR win_per_available_hour IS NULL"))
    add("valid_exposure_denominators", den == 0, {"invalid_rows": den})
    ev = repo.query_df("SELECT evidence_id, source_tables, dataset_fingerprint "
                       "FROM evidence_ledger")
    known = set(counts) | set(CONTRACT_TABLES)
    unknown = sorted({tbl for st in ev.source_tables for tbl in json.loads(st)} - known)
    add("evidence_references_real_sources",
        len(ev) > 0 and not unknown and (ev.dataset_fingerprint == man["fingerprint"]).all(),
        {"records": len(ev), "unknown_sources": unknown})
    run = {"run_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "job_run_id": os.environ.get("DATABRICKS_RUN_ID", "")}
    repo.write_table("validation_summary", pa.Table.from_pylist([{**c, **run} for c in checks]))
    for c in checks:
        print(c["status"], c["check"], c["detail"])
    return 1 if rc != 0 or any(c["status"] == "FAIL" for c in checks) else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", choices=TASKS)
    ap.add_argument("--warehouse-id")
    ap.add_argument("--catalog")
    ap.add_argument("--schema")
    ap.add_argument("--output-dir", default="/tmp/house_of_minds")
    a = ap.parse_args()
    for flag, env in [("warehouse_id", "DATABRICKS_WAREHOUSE_ID"),
                      ("catalog", "DATABRICKS_CATALOG"), ("schema", "DATABRICKS_SCHEMA"),
                      ("output_dir", "HOM_OUTPUT_DIR")]:
        if getattr(a, flag):
            os.environ[env] = getattr(a, flag)
    rc = globals()[a.task]()
    if rc:
        raise SystemExit(rc)  # non-zero exit marks the Databricks task as failed
    return 0


if __name__ == "__main__":
    main()
