# Official challenge alignment and dashboard data handoff

Run: `uv run python scripts/run_challenge.py --backend databricks` (writes `ch_*` tables to `workspace.house_of_minds`). Then `uv run python scripts/export_web_snapshot.py` (writes the JSON export plus manifest for the UI).

## 1. The answer

**Should the manager replace the 10 lowest-earning machines? No: replace none (`REPLACE_NONE`).** The verdict is derived from the evidence; the rule can return all, some, none or insufficient evidence.

| # | Machine | House win | Verdict | Deciding evidence |
| ---: | --- | ---: | --- | --- |
| 1 | M-5076 | $3,573 | INSUFFICIENT_EVIDENCE | 49 days on the floor. A lease nets −$1,698 at the planning value and +$20 only at the best title ever seen in Back Forty |
| 2 | M-1158 | $15,796 | DO_NOT_REPLACE_INSPECT | Payout frequency z = 124 vs game math: a payout fault. Inspect ($1,200) |
| 3 | M-1120 | $16,355 | RETIRED_ALREADY | Retired 2025-05-13 |
| 4 | M-1118 | $20,050 | RETIRED_ALREADY | Retired 2025-02-25 |
| 5–10 | M-1238, M-1181, M-1035, M-1179, M-1017, M-1265 | $24,933–$32,071 | DO_NOT_REPLACE_NOT_ECONOMIC | Back Forty plus low-edge games (Royal Draw / Comet Cash). They earn 0.94–1.10× their same-game peers. A lease loses money even at the zone's best observed title (−$165 to −$593) |

The council independently reproduced every number: 49 claims, all VERIFIED, from the Statistician, Demand Strategist, Operations Chief and CFO. **It reached the same verdict on all 10 machines**, overturning the manager's "replace" decision for all 10. The council *confirmed* the analytics; it did not change them.

**What to do with the $100,000 instead** (same Step 3 economics, horizon Jul 1–30):

| Option | Cost | Modeled net | Range (stated assumption bounds) | Feasible |
| --- | ---: | ---: | --- | --- |
| Manager: lease replacements for the 8 machines still on the floor | $27,040 | **−$15,843** | −$27,399 to −$4,287 | yes |
| Manager: buy 10 | $220,000 | n/a | n/a | **no** (over budget) |
| **Recommended: evidence-supported, 2 promotion weekends** | **$30,000** | **+$62,237** | −$1,506 to +$125,981 (promotion uplift) | yes |
| Conditional upside: + M-1158 inspection + 2 Back Forty → Center Pit moves | $34,800 | +$69,036 | +$5,292 to +$132,780 | yes |
| Optimiser offered a replacement for every on-floor machine | $34,800 | +$69,036 | n/a | yes; **it chose no replacements** |
| No action | $0 | $0 | n/a | yes |

Floor-wide, 68 machines could pay back as replacements only in the best case, and none at the planning value. The best targets are low-edge games in Center Pit and the Main Entrance, not the manager's list.

## 2. Coverage of the six official questions

| Question | Output (UC table) | Key result | Status |
| --- | --- | --- | --- |
| Q1 Fair machine performance and replacement | `ch_manager_bottom10`, `ch_machine_investigation`, `ch_replacement_candidates`, `ch_council_manager_review` | Replace none; 2 retired, 1 inspect, 6 uneconomic, 1 insufficient evidence | Validated |
| Q2 Floor demand | `ch_floor_demand_monthly/weekly`, `ch_zone_demand`, `ch_zone_traffic`, `ch_demand_explanations` | May–Jun coin-in per day −2.1% vs Jan–Apr; per available hour −3.9%, so fewer machines doesn't explain it. Back Forty −31% during the walkway closure, recovered after | Validated |
| Q3 Downtime | `ch_downtime_economics`, `ch_downtime_by_hour` | 5,021 machine-hours; $90,313 theo / $85,509 contribution at risk (not guaranteed loss); worst 21:00–23:00 and May; Ridgeline fails at 3.6× the Halcyon rate after controlling for age | Validated |
| Q4 Tracked players | `ch_player_outcomes`, `ch_player_outcomes_by_tier` | $163.8M wagered, net −$15.6M; 16.1% of players ahead; top 10% = 63.8% of theo (Gini 0.71); carded = 65.8% of coin-in | Validated |
| Q5 Loyalty comps | `ch_loyalty_comps`, `contract_comp_day` | Points per comp dollar halved on 2025-05-01 within every tier; comp cost per day +7.6%; cost per carded theo 1.11% → 1.32% | Validated |
| Q6 $100K actions and measurement | `ch_portfolio_comparison`, `action_measurement_plans`, `decision_passports` | 2 promotion weekends ($30,000), $70,000 kept; stop rules defined | Validated |
| Modeling | `forecast_baseline_comparison`, `holdout_predictions` | Holt-Winters beat the weekday-mean baseline on the May–Jun holdout. **Stored in Delta, not MLflow** (no MLflow models exist) | Validated (Step 5) |

## 3. Backend changes (this run)

- **New:**
  - `analytics/replacement.py` (verdicts, floor-wide candidates, portfolio comparison)
  - `analytics/challenge_questions.py` (Q2–Q5 canonical outputs)
  - `council/manager_review.py`
  - `scripts/run_challenge.py`
  - `contracts/dashboard_contracts.json`
  - `tests/unit/test_challenge.py`
- **Extended (no rewrite):**
  - `optimization/investment_model.py`: replacement economics accept per-machine inputs. Step 3 result hash unchanged (`a56cedddab2060bf`).
  - `council/tools.py`: 5 machine-level allowlisted tools.
  - `council/agents.py`: `review_proposal` for 4 existing agents, using Step 1's Bonferroni thresholds.
  - `council/verifier.py`: accepts the `MANAGER_PROPOSAL` target.
  - `scripts/export_web_snapshot.py`: exports the `ch_*` and forecast tables.
- **Databricks:** 17 new `ch_*` tables (including `ch_validation_summary`). Earlier tables are unchanged (checked).

## 4. Dashboard data handoff

- **Contracts:** `contracts/dashboard_contracts.json` covers all 12 logical contracts: `executive_verdict`, `manager_bottom10`, `machine_investigation`, `replacement_candidates`, `floor_demand`, `downtime_economics`, `player_outcomes`, `loyalty_comps`, `council_audit`, `portfolio_comparison`, `forecast_validation` and `evidence_lineage`. Each lists its source table, grain, keys, units, date semantics, filters, validation, lineage and limitations.
- **How to consume:**
  - Read the JSON export in `web/public/data/current/` (verified by SHA-256 and row counts against the warehouse), or query the UC tables.
  - Verdict, ranking and portfolio tables are **frozen** to the official Jan–Jun window.
  - Date-range exploration uses only daily/weekly/monthly grains, recomputed as ratio-of-sums.
  - Never mix carded and all-play denominators.
  - Machine and bank drill-down: `prepared_daily_view` (`machine_id`, `bank_id`, `zone_id`, `gaming_date`).
  - Player data is exported only as tier and window aggregates.

## 5. Limitations (by importance)

1. **Promotion uplift isn't proven.** It rests on 2 events with no control group. The evidence-supported recommendation is positive at the planning value, but its low end is −$1,506.
2. **Unmeasured effects.** The new-title, inspection-fix and move-transfer effects are planning assumptions. The replacement verdicts hold even at the evidence ceiling, except M-5076 (+$20 best case).
3. **July-only scope.** Replacement benefits count only July (official horizon). Longer-run payback is out of scope.
4. **One council rule can't be cross-checked.** The council reproduces exposure but not "short tenure with normal per-hour demand" (no tool). It didn't apply to these 10 machines.
5. **No MLflow.** The forecasting model lives in Delta, and its metrics differ slightly across SciPy/NumPy versions (decisions agree).
