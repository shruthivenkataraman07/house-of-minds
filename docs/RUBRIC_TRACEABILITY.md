# Rubric traceability

How each judging criterion is supported, tested and still outstanding. Status as of Phase 1, Step 1 (data foundation). **No criterion is claimed as fulfilled.** The dashboard, model, recommendation and final originality claim do not exist yet.

Points are not earned by chart count, model complexity, agent count or number of findings. Each item below is here because it supports validity, a decision, or traceability.

## Analytical validity (30%)

| Requirement | Step 1 deliverable | Verified by | Downstream dependency |
| --- | --- | --- | --- |
| Correct money math | Metric registry ([METRIC_REGISTRY.md](METRIC_REGISTRY.md)); integer-cent source of truth | R01, R02, R03, R08, R14; `tests/unit/test_metrics.py` | Every engine and dashboard number uses `analytics/metrics.py` |
| Ratio of sums, not mean of ratios | `MACHINE_AGGREGATES_SQL`, `ratio_of_sums` | `test_ratio_of_sums_differs_from_mean_of_ratios` | Dashboard hold KPIs |
| Gaming day and DST | `gaming_date_sql`, `scheduled_seconds` exposure | R13; `tests/unit/test_gaming_day.py` | Hourly and event analyses |
| Fair comparison: exposure, availability, luck | `analytics/machine_performance.py`: 4 rankings, exact shortfall decomposition, luck z from game-math variance | `test_decomposition_is_exact`, `test_off_floor_days_excluded`, R04, R05 | Machine engine, optimizer targets |
| Uncertainty shown | Bootstrap 90% interval and P(bottom-10); HAC CIs; Poisson CIs; Bonferroni-adjusted p-values | `test_rankings_and_bootstrap` | Dashboard error bars |
| Competing explanation tested | Luck (Q1 → Q2 persistence), luck vs leak (hit-rate test), seasonality vs closure (ratio design), age vs manufacturer (Poisson), tier mix vs price change | `reports/investigations.json`, evidence records | Council cross-examination |
| No join inflation | Interval-join placements; guest tables aggregated before joining | R06, R07; join-cardinality report | All engines |

## Dashboard and communication (25%)

| Requirement | Step 1 deliverable | Downstream |
| --- | --- | --- |
| Clear metric definitions | [METRIC_REGISTRY.md](METRIC_REGISTRY.md), generated from code | Tooltips and glossary |
| Understandable findings | `reports/analytical_findings.md` (question → evidence → competing explanation → relevance) | Narrative order of dashboard pages |
| Traceable claims | 31 evidence records with deterministic `EV-` ids and a dataset fingerprint | Every chart and claim cites an `evidence_id` |
| Typed outputs | Six Pydantic contracts (`backend/schemas/contracts.py`); every row validated | FastAPI responses and React types |
| Accessible visuals | **Not started** | Step 3+ |

## Modeling and validation (20%)

| Requirement | Step 1 deliverable | Verified by | Outstanding |
| --- | --- | --- | --- |
| Sensible, decision-linked target | Daily floor coin-in → staffing and promotion timing ([MODELING_PLAN.md](MODELING_PLAN.md)) | n/a | Train in Step 2 |
| Simple baseline | Constant mean and weekday mean defined | n/a | Compute and freeze |
| Time-based holdout | Jan–Mar / Apr / May–Jun split | `test_temporal_split` (unit and integration) | Score once |
| No leakage | Feature registry with `known_at_origin`; `assert_no_leakage` | `test_leaky_features_blocked` | Enforce in training code |

## Recommendations and tradeoffs (15%)

| Requirement | Step 1 deliverable | Verified by | Outstanding |
| --- | --- | --- | --- |
| Correctly priced interventions | `optimization/action_catalog.py`, the GUIDE formula in cents | Guide example $3,380 reproduced; `tests/unit/test_action_catalog.py` | Benefit estimates |
| Valid allocation constraints | Budget, quantity limits, ≤3 types, A-HOLD free, comp-policy and same-machine conflicts, lead-time operating days | 10 unit tests plus `test_official_catalog_pricing` | Optimizer (Step 2+) |
| Sensitivity inputs | Lost-theo estimates with CIs (closure, Ridgeline downtime, M-1158 leak per day) | `reports/investigations.json` | Sensitivity analysis |
| Measurement plan | Not started | n/a | Per-action measurement plan |

## Originality (10%)

Candidate findings with reproducible evidence. Not yet claimed as the submission's "unexpected finding":

1. M-1158's payout frequency is inconsistent with its game math (hit-rate z = 124); a raw bottom-10 "replace" candidate is really an "inspect" candidate.
2. A temporary walkway closure cut Back Forty demand by about 31% and inflates its machines' bad rankings.
3. The comp points price halved within every tier on 2025-05-01, while comp cost per day rose 7.6%.

Outstanding: choose one finding, connect it to a funded action, and test it again in Step 2.

## Reproduce

```sh
uv run python scripts/run_step1.py   # regenerates every report and evidence record (~6 s)
uv run pytest tests                  # 85 tests: unit, plus integration on the official data
```
