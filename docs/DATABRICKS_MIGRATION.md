# Databricks migration design (Phase 2)

Status (2026-11-07): **running on Databricks Free Edition** (`https://dbc-cf3e3b85-f118.cloud.databricks.com`, profile `HOUSE_OF_MINDS_FREE`, warehouse `cf173e33d1a9762c`, schema `workspace.house_of_minds`). The original workspace (`dbc-f153929c-62ed`) became serverless-ineligible and is no longer used.

## Phase 2 / Step 2 results

| Item | Evidence |
| --- | --- |
| 31 official files in volume `raw` | 31/31 SHA-256 match the official manifest |
| 31 bronze Delta tables | 31/31 row counts match the manifest |
| Reconciliation on Databricks | 14/14 pass; every calculated value equals the local run (within $0.01 or 1e-9) |
| Equivalence gates (`scripts/compare_backends.py`) | PASS: contract tables (money within $0.01, other floats relative 1e-6), reconciliation, evidence IDs (31/31 identical) |
| Job `house-of-minds-step2-pipeline` (ID 976658855400592), 5 dependent tasks | Run 411075602890645: SUCCESS; `validation_summary` 6/6 PASS. Manual trigger only |

Run again: `databricks bundle run step2_pipeline -t dev` (re-verifies sources; never reloads them).

## Principle

Analytical definitions live in one place and run unchanged: the formulas in `analytics/metrics.py`, the check logic in `pipelines/validation/reconciliation.py`, and the schemas in `backend/schemas/contracts.py` and `evidence/schema.py`. Phase 2 swaps **where tables live and what executes the SQL**, not what the SQL means.

## Separation already in place

| Concern | Module | Storage-specific? |
| --- | --- | --- |
| Source registry (names, grains, keys) | `pipelines/ingestion/catalog.py` | No; only `relative_path` is local |
| Source reading | `pipelines/ingestion/loader.py` | Yes, the only local-file reader |
| Data access contract | `backend/repositories/base.py` (`AnalyticsRepository`) | No |
| Local implementation | `backend/repositories/duckdb_repo.py` | Yes |
| Databricks implementation (stub) | `backend/repositories/databricks_repo.py` | Yes |
| Metric formulas | `analytics/metrics.py` | No (SQL over unqualified table names) |
| Analyses and contracts | `analytics/*.py` | No; they take a repository |
| Financial rules | `optimization/action_catalog.py` | No |
| Evidence schema and store | `evidence/schema.py`, `evidence/recorder.py` | Store only |
| API schemas | `backend/schemas/contracts.py` | No |

## Component mapping

| Local (Phase 1) | Databricks (Phase 2) | Notes |
| --- | --- | --- |
| Parquet files in `data/raw` | UC volume `/Volumes/workspace/house_of_minds/raw/` (unchanged files, same SHA-256) | Re-run `build_manifest` against the volume copy; the fingerprint must match `4792a8a179571d7b` |
| DuckDB views per table | Delta bronze tables `workspace.house_of_minds.<table>` | Same table names; `DatabricksRepository` sets `USE CATALOG/SCHEMA` |
| DuckDB SQL in `analytics/` | Databricks SQL warehouse (`490ef3abcd3bd599`) | Dialect gaps to handle: `strftime`, `date_diff`, `FILTER (WHERE)`, `approx_count_distinct`; keep a small dialect shim in the repository rather than forking formulas |
| pandas post-processing (bootstrap, OLS, Poisson) | Same Python on the client, or PySpark for scale | Inputs are small aggregates; scale doesn't require Spark here |
| `scripts/run_step1.py` | Lakeflow Job with tasks: manifest → profile → reconcile → analyses → contracts | Each task writes Delta outputs; the job fails if any reconciliation check fails |
| `data/processed/contract_*.parquet` | Delta gold tables `contract_*` | Schemas from `backend/schemas/contracts.py` |
| `data/processed/evidence_ledger.jsonl` | Delta table `evidence_ledger`, primary key `evidence_id` | MERGE on `evidence_id`; ids are deterministic, so reruns upsert |
| Local MLflow (`sqlite:///mlflow.db`) | MLflow on Databricks, models in Unity Catalog (`databricks-uc`) | Log split definition, baselines and holdout metrics as run params/metrics |
| Folder permissions | Unity Catalog grants | Read-only `raw`; write `gold` and `evidence` for the job's service principal only |

## Equivalence acceptance gates

Phase 2 is done only when, run on Databricks:

1. All 14 reconciliation checks pass with the same tolerances.
2. For every contract table, row counts match and numeric columns agree within $0.01 (money) or 1e-9 (ratios) with the Phase 1 Parquet outputs.
3. Evidence IDs for the same calculations are identical (same fingerprint, same calculation ids).
4. The integration test suite runs against `DATA_BACKEND=databricks`.

## Cost controls

The serverless warehouse auto-starts on query. Creating the schema, uploading data, starting the warehouse and scheduling jobs each need explicit approval (see `CLAUDE.md`).
