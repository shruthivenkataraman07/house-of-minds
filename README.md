# The House of Minds

Casino decision intelligence for the TAMU Datathon **Dashboard Royale** challenge and the Databricks track.

> Status: Phase 1, Step 1 (data foundation) complete. Dashboard, model, optimizer and agents are not built yet.

## Quick start

```sh
brew install uv node libomp databricks/tap/databricks   # prerequisites (macOS)
scripts/setup.sh          # install Python + frontend deps from lockfiles
scripts/fetch_data.sh     # download the challenge dataset into data/raw (~1 GB)
scripts/verify.sh         # lint, type-check, test, build
scripts/dev.sh            # backend on :8000, frontend on :5173
```

## Phase 1, Step 1: data foundation

```sh
scripts/fetch_data.sh                    # official dataset -> data/raw (read-only)
uv run python scripts/run_step1.py       # manifest, profile, 14 reconciliation checks,
                                         # machine comparison, investigations, contracts
uv run pytest tests                      # unit + integration tests on the real data
```

| Output | What it is |
| --- | --- |
| `reports/dataset_manifest.json` | Files, sizes, SHA-256 vs the official manifest, dataset fingerprint |
| `reports/data_profile.json`, `reports/data_quality_summary.md` | Profiling, classified findings, referential integrity, join risks, reconciliation |
| `reports/reconciliation.json` | Each check: inputs, result, expected relationship, tolerance, status |
| `reports/machine_comparison.md` / `.csv` | Raw vs exposure vs luck-aware vs peer rankings, decomposition, persistence test |
| `reports/investigations.json` | Payout anomaly, walkway closure, downtime, comp-rate change |
| `reports/analytical_findings.md` | Concise findings report with evidence IDs |
| `data/processed/contract_*.parquet` | Six validated domain contract tables |
| `data/processed/evidence_ledger.jsonl` | Evidence records (deterministic ids) |
| `docs/METRIC_REGISTRY.md`, `docs/MODELING_PLAN.md`, `docs/DATABRICKS_MIGRATION.md`, `docs/RUBRIC_TRACEABILITY.md` | Definitions and plans |

## Layout

| Path | Purpose |
| --- | --- |
| `frontend/` | React + TypeScript + Vite dashboard |
| `backend/` | FastAPI app: `api/` routers, `services/`, `schemas/`, `repositories/` (storage abstraction) |
| `pipelines/` | Ingestion, validation, transformations |
| `agents/`, `council/`, `evidence/` | Specialist agents, adversarial council, evidence ledger |
| `models/`, `simulation/`, `optimization/` | Forecasting, Monte Carlo, budget optimization |
| `dashboard/` | Dashboard-specific data contracts |
| `analytics/` | Metric registry, machine comparison, investigations, contract builders |
| `config/` | Typed settings (`config/settings.py`) |
| `databricks/` | Phase 2 bundles, jobs, and SQL |
| `tests/` | `unit/`, `integration/`, `e2e/` |
| `docs/` | Setup, Databricks, troubleshooting, AI-use log |

## Storage abstraction

Services depend on `backend.repositories.base.AnalyticsRepository`. `DATA_BACKEND=duckdb` (Phase 1) uses
`DuckDBRepository`; `DATA_BACKEND=databricks` (Phase 2) switches to `DatabricksRepository` without changing services.

See [docs/SETUP.md](docs/SETUP.md), [docs/DATABRICKS.md](docs/DATABRICKS.md), and [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).
