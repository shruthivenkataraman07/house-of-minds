# Step 5: The Proving Grounds

## A. Execution

| | |
| --- | --- |
| Start / protocol frozen | 2026-11-07 19:59:37 / 20:00:11 (before any model fit) |
| End | 2026-11-07 20:13:53 (about 14 minutes) |
| Commands | `uv run python scripts/run_step5.py [--backend databricks]`; job `house-of-minds-step5-proving-grounds` (ID 135772365852291), final run **1048055762772498: TERMINATED / SUCCESS** |
| Git commit | None: the repository has no commits (not authorised). Provenance uses the protocol SHA-256 `939dfc9f…`, `code_hash` and the canonical snapshot `chf-v1:bc5e8ccc5d88a490` |
| Execution mode | Forecasting: statsmodels Holt-Winters (real model). Council: RULE_BASED (unchanged). No LLM calls, $0 inference |

## B. Evaluation design (pre-registered: `docs/STEP5_EVALUATION_PROTOCOL.md`)

- **Target:** daily floor theo (USD/gaming day). Changed from the Step 1 plan's coin-in before training, because the decision input is in theo.
- **Splits:** train Jan–Mar (selection), validation Apr, final holdout May 1–Jun 30 (61 days, horizons 1–61, issued end of Apr 30, scored once).
- **Baseline:** weekday mean of the training window.
- **Candidate:** Holt-Winters, additive weekly seasonality. Trend selected on April: damped additive (validation MAE $4,036 vs $4,062 with no trend).
- **Intervals:** validation residual 10th/90th percentiles.

## C. Forecast results (61 holdout days, same rows)

| | Baseline | Holt-Winters |
| --- | ---: | ---: |
| MAE | $6,699 | **$5,836 (−12.9%)** |
| RMSE | $8,299 | $7,584 |
| Bias (forecast − actual) | +$4,029 | +$2,365 |
| WAPE | 5.2% | 4.6% |
| MAE, non-event days (51) | $6,328 | $5,176 |
| MAE, event days (10) | **$8,591** | $9,204 |
| 80% interval coverage | n/a | **60.7%** (nominal 80%) |

**Error analysis:**
- Both methods over-forecast, because May–June demand ran below January–April levels. Holt-Winters' damped trend absorbs part of that.
- The largest errors fall on EDC (Sat May 17, under-forecast by about $25k) and on late-June weekends (over-forecast).
- On event days the candidate is *worse* than the baseline: neither model knows about events.
- The intervals are too narrow. Validation residuals (1–30 days ahead) understate 31–61-day error and the May–June level shift. They should not be treated as calibrated.

**Leakage tests:** forecasts inside the training window or with gaps are refused. Poisoning the future leaves forecasts unchanged. Event counterfactuals use only pre-event data.

## D. Decision impact (existing Step 3 optimiser, only A08 varied)

**Mapping:** promotion value = 3 × A08 × 0.9468 − $15,000. A08 = actual theo − counterfactual theo on Fri–Sun promotion days. Break-even: **$5,281/day**. Step 3 estimated the counterfactual with a ±28-day window that includes *post-event* days. Step 5 re-estimates it with past-only methods.

| Excess per event (USD/day) | Step 3 window | Baseline (past-only) | **Holt-Winters (past-only)** |
| --- | ---: | ---: | ---: |
| Locals Week (Jun 9–15) | 5,016 | **3,521** | **11,729** (80% lower bound 6,908) |
| Winter Tournament (Feb 21–23) | 27,458 | 27,875 | 19,901 |
| Mean (planning value) | 16,237 | 15,698 | 15,815 |

| Decision (evidence-supported mode) | Step 3 window | Baseline | Holt-Winters |
| --- | --- | --- | --- |
| At the mean | 2 promotions, $62,237 | 2 promotions, $59,175 | 2 promotions, $59,840 |
| At the weaker event | **HOLD** | **HOLD** | **2 promotions, $36,627** |

**Finding:**
- The decision at the planning value is stable across all counterfactual methods.
- The weak-event reversal from Steps 3 and 4 **depends on the counterfactual method.** It appears with the symmetric window and the simple past-only baseline. It disappears with the better-validated forecast (lower holdout MAE), even at its pessimistic 80% bound.
- This improves the *measurement* of an association. It does not identify a causal promotion effect: there are still 2 events, no control group, and under-covering intervals. Modeled contribution is not realised profit.

## E. Council evaluation (recomputed from persisted Step 4 records)

| Configuration | Independent objections | Retractions | Unresolved hypotheses | New evidence checks | Duplicates suppressed | Portfolio-impact rows changed | Runtime |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A: optimiser only (Step 3) | 0 | 0 | 0 | 0 | 0 | 0 | n/a |
| B: best single specialist (Statistician) | 1 | 0 | n/a | 0 | 0 | 1 | 0.13 s |
| C: six specialists, no gossip | 3 | 0 | 2 | 0 | 0 | 2 | 0.31 s |
| D: six specialists + Whisper Network | 3 | **1** | **1** | **3** | **1** | 2 | 0.53 s |

- All six agents are RULE_BASED, not LLM agents.
- The one decision-changing challenge comes from the Statistician alone; Demand and CFO each add one independent non-changing objection.
- Gossip improved claim hygiene (1 retraction, 4 flagged dependents, 3 checks) at about 1.7× runtime. It found **no** additional independent objection and the **same** portfolios.
- These are single deterministic runs: a description, not a significance test.

**Known-answer verifier set:** 10 of 10 correct.
- **3 SUPPORTED** (real, reproduced from tools) were accepted.
- **4 REFUTED** (synthetic: misstated value, invented figure, fake evidence ID, invalid action) were rejected.
- **3 UNRESOLVED** (causal promotion claim, inspection-fix hypothesis, comp attribution) were left inconclusive.
- Overhead is about 0.4 ms per claim.
- Labels come from construction and source identities, not from earlier verifier outputs. This is still a small fixture set.

## F. Promotion fragility

- **Reproduced:** break-even $5,281.1/day; the weak observation is $5,015.87/day; the evidence portfolio becomes HOLD at that value.
- **Weekend SD:** the ordinary-weekend SD ($4,649) describes demand noise. It is **not** used as a causal interval.
- **Conclusion:** the evidence cannot distinguish between economically different choices. The forecast-based re-measurement favours running the promotions, but only associationally.
- **Measurement design** (`action_measurement_plans`):
  - Use a pre-registered Holt-Winters counterfactual and net out the following week's displacement.
  - If feasible, add a carded-guest holdout group for the mailer.
  - Stop rule: if the first weekend falls below break-even outside the 80% band, cancel the second weekend before its 14-day lead closes.

## G. Robustness

- **Step 3 scenarios:** all 13 re-run and reproduce exactly, with the same portfolios and regret (baseline optimal in 10 of 13, maximum regret $3,636).
- **Forecast-informed tests:** 14 tests vary A08 per counterfactual method and statistic. Changes occur only at the weak-event value under the two non-forecast methods.
- **Unresolved:** inspection fix probability, move demand transfer, and causal promotion uplift.

## H. Snapshot consistency

- **Root cause:** assumption A07 is computed from `contract_comp_day` on Databricks but from a fallback query locally. The values differ by 3×10⁻¹⁵ relative, and the old fingerprint hashed raw floats.
- **Fix:** canonical contract `chf-v1` (`models/canonical.py`): sorted fields, Decimal quantisation by unit (money 0.01, ratios 1e-6, counts 1), and the version plus unit map in the payload.
- **Result:** local and Databricks both give `chf-v1:bc5e8ccc5d88a490`.
- **Historical fingerprints preserved:** `991446d9…` (local) and `de50d70f…` (Databricks).

## I. Databricks AI/BI preparation

- **Tables:** `model_evaluation_runs`, `holdout_predictions`, `forecast_baseline_comparison`, `decision_model_impact`, `promotion_counterfactuals`, `council_ablation_results`, `agent_reliability_evaluation`, `decision_robustness_results`, `action_measurement_plans`, `aibi_metric_definitions` (8 trusted metrics: formula, unit, source, dimensions, limitations), `step5_validation_summary`.
- **Views:** `v_model_accuracy`, `v_decision_impact`, `v_council_ablation`, `v_portfolio_robustness`.
- **Native features:** AI/BI dashboards API reachable (none created). Genie is available (a sample space exists; `create-space` is supported). **Genie has not been configured for House of Minds.**

## J. Rubric mapping

| Criterion | Weight | Step 5 evidence |
| --- | ---: | --- |
| Analytical validity | 30% | Past-only counterfactuals; association vs causation kept separate; measurement intervals not used as causal intervals |
| Dashboard and communication | 25% | Metric definitions plus four serving views; concise decision tables |
| Modeling and validation | 20% | Holt-Winters vs baseline on an untouched chronological holdout; pre-registered protocol; leakage tests; metrics reproduce from persisted rows |
| Recommendations and tradeoffs | 15% | Forecast linked to A08 → optimiser; budget and type limits kept; measurement plans with stop rules |
| Originality | 10% | Shows that the Step 3/4 reversal depends on the counterfactual method; council ablation with origin-deduplicated objections |

### Cross-environment forecast reproducibility (gate 41: FAIL, recorded)

| | Local | Databricks (statsmodels 0.15.0 pinned) |
| --- | ---: | ---: |
| Libraries | SciPy 1.18.1, NumPy 2.5.4 | SciPy 1.13.1, NumPy 1.26.4 (serverless core; cannot be pinned) |
| Holt-Winters holdout MAE | $5,836 (−12.9% vs baseline) | $5,552 (−17.1%) |
| Baseline MAE | $6,699 | $6,699 (identical) |
| Locals Week HW excess / 80% lower bound | $11,729 / $6,908 | $11,731 / $6,937 |

- **What differs:** Holt-Winters maximum-likelihood estimates depend on optimiser versions. An unpinned first Databricks run gave a holdout MAE of $5,159.
- **What doesn't:** the model beats the baseline in every environment, and **all 20 decision rows select identical portfolios** (gate 42 PASS).
- **Status:** forecast *metrics* are not bit-reproducible across platforms; *decisions* are. Library versions are now stored in `model_evaluation_runs.library_versions`. Switching to a version-independent estimator now would be a post-hoc protocol change, so it is listed as a Step 6 option.

## K. Acceptance checks

- **Local:** 42 of 42 PASS (gate 41 writes the reference).
- **Databricks (run 1048055762772498):** 41 PASS, 1 FAIL (gate 41, cross-environment forecast agreement), 0 BLOCKED.
- Gates 1–40 and 42 all PASS on both platforms. See `step5_validation_summary`.

## L. Step 6 handoff

- **Tables:** `forecast_baseline_comparison`, `holdout_predictions`, `decision_model_impact`, `promotion_counterfactuals`, `council_ablation_results`, `agent_reliability_evaluation`, `decision_robustness_results`, `action_measurement_plans`, `aibi_metric_definitions`, plus the Step 1–4 tables.
- **Limitations to carry forward:**
  - 2 promotion events, no control group.
  - Under-covering intervals.
  - Rule-based council.
  - Unknown inspection, move and uplift effects.
  - No git commits.
  - Forecast metrics not bit-reproducible across SciPy/NumPy versions (decisions are).
  - `scripts/` is outside the mypy scope (11 typing messages in `run_step5.py`).
