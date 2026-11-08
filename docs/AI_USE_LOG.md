# AI-use log

The Dashboard Royale submission requires an AI-use disclosure. Record each use here as you go.

| Date | Tool | What it was used for | Human review |
| --- | --- | --- | --- |
| 2026-11-07 | Claude Code (VS Code) | Step 1 environment setup: tool installs, dependency resolution, project skeleton, config, verification tests | Reviewed by team |
| 2026-11-07 | Claude Code (VS Code) | Phase 1 Step 1: data ingestion, profiling, reconciliation checks, metric registry, machine comparison, investigations, contracts, modeling and Databricks plans; all numbers computed by code from the official data | Reviewed by team |
| 2026-11-07 | Claude Code (VS Code) | Phase 2 start: Databricks schema/volume, file upload and hash verification, Databricks repository, portable SQL, bronze loader, equivalence checker, job bundle (blocked by inactive account) | Reviewed by team |
| 2026-11-07 | Claude Code (VS Code) | Step 2 finalization on Databricks Free Edition: bronze load, Databricks validation run, equivalence gates, 5-task job, evidence provenance fix | Reviewed by team |
| 2026-11-07 | Claude Code (VS Code) | Step 3: investment candidates, assumption registry, MILP optimiser, decision-reversal engine, scenarios/regret, evidence links, Step 3 Databricks job | Reviewed by team |
| 2026-11-07 | Claude Code (VS Code) | Step 5: pre-registered forecast protocol, Holt-Winters vs baseline holdout, past-only promotion counterfactuals into the Step 3 optimiser, council ablation, known-answer verifier set, canonical hash contract, AI/BI views, Step 5 job | Reviewed by team |
| 2026-11-07 | Claude Code (VS Code) | Step 6: decision passports, claims registry, evidence dependency graph, invalidation impact, accountability/AI audit/reproducibility, serving datasets, semantic contract, generated submission docs | Reviewed by team |

## Hardening audit (2026-11-07)
AI assistant (Claude Code) wrote `scripts/run_audit.py` and `docs/HARDENING_AUDIT.md`: an independent re-derivation of the replacement verdicts, sensitivity tests and promotion scenarios. No production calculations were changed. All outputs are sidecar JSON in `reports/audit/`.

## Dashboard build (2026-11-07)
AI assistant (Claude Code) built the Next.js dashboard in `web/src/` (views, the deterministic Ask the House router, data adapters and tests) and wrote `scripts/export_dashboard_sidecar.py`. All displayed figures come from the verified exports; no LLM is called at runtime.

## Product transformation (2026-11-08)
AI assistant (Claude Code) built the FastAPI dashboard API (`backend/api/v1.py`, `backend/services/`, `backend/schemas/api.py`). It ported the Ask the House router to Python and rebuilt the React views as a light-theme static app served by FastAPI. It also added `Dockerfile` and `docs/DEPLOYMENT.md`. No analytical results were recalculated; live mode reads the existing Unity Catalog tables.

## Plain-language explanations and typeset formulas (2026-11-08)
AI assistant (Claude Code) rewrote the dashboard's calculation explanations in plain language (`web/src/lib/explain.ts`, `web/src/components/explain.tsx`). It added typeset formulas, rendered with KaTeX from fixed templates in `web/src/lib/formulas.ts`, to the evidence passports and the "How this is calculated" panels. The passport API now exposes the recorded numeric operands (`values`). No calculation or recorded value was changed; substituted numbers come from API fields only.
