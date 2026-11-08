# Reproducibility guide

Generated from `reproducibility_manifest`.

## Re-run everything

```sh
scripts/setup.sh && scripts/fetch_data.sh
uv run python scripts/run_step1.py                       # local foundation
uv run python scripts/run_step1.py --backend databricks  # bronze + Step 2
databricks bundle deploy -t dev
databricks bundle run step2_pipeline -t dev
databricks bundle run step3_decision_engine -t dev
databricks bundle run step4_whisper_council -t dev
uv run python scripts/run_step5.py   # writes the local forecast reference
databricks bundle run step5_proving_grounds -t dev
databricks bundle run step6_evidence_vault -t dev
```

## Manifest

| Item | Value | Note |
|---|---|---|
| repository_commit | NONE (no commits authorised) | content hashes used instead |
| dataset | Dashboard Royale 4792a8a179571d7b (manifest fingerprint) | 31 official tables, SHA-256 verified (Step 1/2) |
| canonical_snapshot | chf-v1:bc5e8ccc5d88a490 | chf-v1 contract; matches local and Databricks |
| historical_fingerprints | 991446d9be867b7c (local), de50d70f0b78336b (Databricks) | preserved, not rewritten |
| step5_protocol_sha256 | 939dfc9ff4ee4aa65c7cb552241d4fd90964269d7167ede59f76ee36a7432308 | pre-registered before fitting |
| step5_library_versions | {"statsmodels": "0.15.0", "scipy": "1.13.1", "numpy": "1.26.4", "pandas": "1.5.3", "python": "3.12.3"} | HW MLE differs across SciPy/NumPy versions |
| precision_rules | source cents (integer); USD 2dp in outputs; ratios full float; canonical hash quantises money 0.01, ratios 1e-6 | no financial value altered for hashing |
| job:step2 | {"job_id": 976658855400592, "run_id": 411075602890645} | Databricks job |
| job:step3 | {"job_id": 670548312985484, "run_id": 4424786631438} | Databricks job |
| job:step4 | {"job_id": 15426832427505, "run_id": 410566497924336} | Databricks job |
| job:step5 | {"job_id": 135772365852291, "run_id": 1048055762772498} | Databricks job |
| table:action_measurement_plans | 3 | row count at Step 6 |
| table:agent_claims | 23 | row count at Step 6 |
| table:agent_reliability_evaluation | 10 | row count at Step 6 |
| table:agent_reliability_summary | 12 | row count at Step 6 |
| table:aibi_metric_definitions | 8 | row count at Step 6 |
| table:claim_verification_results | 23 | row count at Step 6 |
| table:council_ablation_results | 4 | row count at Step 6 |
| table:council_decision_events | 99 | row count at Step 6 |
| table:council_portfolio_impacts | 8 | row count at Step 6 |
| table:council_runs | 2 | row count at Step 6 |
| table:council_validation_summary | 61 | row count at Step 6 |
| table:council_whispers | 16 | row count at Step 6 |
| table:decision_evidence_links | 22 | row count at Step 6 |
| table:decision_model_impact | 20 | row count at Step 6 |
| table:decision_reversals | 14 | row count at Step 6 |
| table:decision_robustness_results | 27 | row count at Step 6 |
| table:evidence_ledger | 31 | row count at Step 6 |
| table:forecast_baseline_comparison | 3 | row count at Step 6 |
| table:holdout_predictions | 61 | row count at Step 6 |
| table:intervention_assumptions | 10 | row count at Step 6 |
| table:investment_candidates | 18 | row count at Step 6 |
| table:machine_comparison | 310 | row count at Step 6 |
| table:model_evaluation_runs | 1 | row count at Step 6 |
| table:optimization_runs | 5 | row count at Step 6 |
| table:optimizer_validation_summary | 20 | row count at Step 6 |
| table:portfolio_allocations | 13 | row count at Step 6 |
| table:portfolio_regret | 1 | row count at Step 6 |
| table:promotion_counterfactuals | 6 | row count at Step 6 |
| table:reconciliation_results | 14 | row count at Step 6 |
| table:scenario_results | 13 | row count at Step 6 |
| table:step5_validation_summary | 42 | row count at Step 6 |
| table:validation_summary | 6 | row count at Step 6 |

Known limitation: Holt-Winters metrics differ across SciPy/NumPy versions (local 5,836 vs Databricks 5,552 MAE); all decisions agree (Step 5 gate 42).
