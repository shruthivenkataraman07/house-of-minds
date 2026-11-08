# Hardening audit: replacement decision and portfolio robustness

- **Re-run:** `uv run python scripts/run_audit.py`
- **Outputs (sidecar, read-only with respect to production):** `reports/audit/`
  - `a1_independent_bottom10.json`
  - `a3_a4_verification.json`
  - `b_inputs.json`
  - `b4_robustness_matrix.json`
  - `c_promotion_portfolio.json`
  - `d_council_forecast.json`
- **No production calculation, table, contract or export was changed.**

## 1. Is the manager's bottom 10 reproduced? Yes

An independent query of the raw parquet files (no project functions) returns the same 10 machines in the same order:

> M-5076, M-1158, M-1120, M-1118, M-1238, M-1181, M-1035, M-1179, M-1017, M-1265

- **Checks:** house win, coin-in − payout and theo all differ by 0 cents. The window is 2025-01-01..06-30 (181 days).
- **Hold must be ratio-of-sums.** A mean of daily hold gives different answers (M-5076: 0.0239 vs −0.0012), so averaging daily hold would be wrong.

## 2. Are the verdicts independently verified?

The audit re-derived each machine's verdict from raw SQL: retire date, hit-rate z, own theo per available hour from 2025-04-07, zone ceiling, and lease net from catalog terms ($2,500 + $55/day × 16 days = $3,380; 6 h downtime).

The audit's verdict matched production for all 10 machines. Lease net differs from production by $0.00.

| Machine | Verdict | Classification | Depends on |
| --- | --- | --- | --- |
| M-1120, M-1118 | RETIRED_ALREADY | VERIFIED | retire_date (2025-05-13, 2025-02-25) |
| M-1158 | DO_NOT_REPLACE_INSPECT | VERIFIED | hit z = 124.2 vs game math |
| M-1238, M-1181, M-1035, M-1179, M-1017, M-1265 | DO_NOT_REPLACE_NOT_ECONOMIC | VERIFIED WITH ASSUMPTIONS | ceiling = zone's best observed title; July-only horizon; floor-average contribution factor |
| M-5076 | INSUFFICIENT_EVIDENCE | VERIFIED WITH ASSUMPTIONS | best case +$20 sits on the boundary |

There were no disagreements. The audit did, however, recompute with the same economic definitions that production uses. It confirms the arithmetic and the rules, not that those definitions are correct.

## 3. How robust is "replace none"?

See `b4_robustness_matrix.json`.

**REPLACE_NONE is ROBUST within the official horizon.** No on-floor machine is positive at the planning value under any tested variant. The best planning net is −$1,241. The variants tested:
- the base case;
- conservative: A10 = 0.25 with 25% cannibalization;
- a lease-class-adjusted contribution factor.

**The split between "not economic" and "insufficient evidence" is CONDITIONAL.**
- **Lease-class factor.** This variant assumes the new title carries no revenue share and the outgoing revenue-share machine's 20% share is saved. Under it, the best case turns positive for:
  - M-1181: +$282
  - M-1265: +$374
  - M-5076: +$182

  Those two machines would then be classed INSUFFICIENT_EVIDENCE rather than NOT_ECONOMIC.
- **Zone ceiling +10%.** 5 of 6 best cases turn positive. Only M-1179 stays negative in every test, so it is the only one classed ROBUST.
- **Not treated as a defect.** The catalog does not say whether a leased title pays revenue share. Production therefore keeps the floor-average factor.

**M-5076:**
- **July break-even:** A10 = 0.99, meaning the new title must capture 99% of the gap to the best title ever seen in Back Forty.
- **Classification:** INSUFFICIENT EVIDENCE. It has only 49 days on the floor.

**Horizon dependence (material).**
- **Within July, the verdict holds.** The catalog says a lease "runs for the remainder of the horizon", so a 16-day horizon is the correct reading.
- **After July, replacements could pay back.** At the planning value A10 = 0.5, every replacement nets +$34 to +$52 per day in steady state and pays back in **48–76 days**. Steady-state break-even is A10 ≈ 0.26–0.31.
- **So the answer is horizon-specific.** "Not economic" means "not economic in July". For a longer horizon the answer would be "conditional on an unmeasured title effect", not "no".

**Incremental definition (verified).** The benefit is (ceiling − own rate) × hours × A10 × factor, less downtime and cost. It counts only the improvement over the machine's own rate, not the new title's total revenue.

## 4. What does −$1,506 mean?

It is the evidence portfolio's total net at the weakest of the two observed promotion events, A08 = $5,015.87/day: 2 × (3 × 5,015.87 × 0.9468 − 15,000). It is one scenario value, not a confidence bound. With only two events, the min and max are not a calibrated interval.

| A08 scenario ($/day excess theo) | Evidence portfolio (2 promos) | Conditional portfolio | Conditional, promo removed |
| --- | ---: | ---: | ---: |
| Zero uplift (0) | −$30,000 | −$23,201 | +$6,799 |
| Weakest event (5,016) | −$1,506 | +$5,292 | +$6,799 |
| **Break-even (5,281)** | $0 | +$6,799 | +$6,799 |
| Base / mean (16,237) | +$62,237 | +$69,036 | +$6,799 |
| Strongest event (27,458) | +$125,981 | +$132,780 | +$6,799 |

**Re-optimizing with promotions prohibited:**
- Evidence mode → HOLD ($0).
- Conditional mode → inspect M-1158 + 2 moves to Center Pit, +$6,799 for $4,800.

**Other options:**
- Manager lease (8 machines): −$15,843. It is negative at every A10 value from 0 to 1 (−$27,399 to −$4,287).
- No action: $0.

| Action | Classification | Why |
| --- | --- | --- |
| Promotion × 2 | **CONDITIONAL ON ASSUMPTIONS** | Positive in 3 of 5 scenarios. Rests on 2 events with no control group; the break-even sits just above the weakest event |
| Inspect M-1158 | CONDITIONAL ON ASSUMPTIONS | +$1,549 at A01 = 0.5 fix probability. The fault itself is VERIFIED (z = 124) |
| Move M-1154 / M-1184 → Center Pit | CONDITIONAL ON ASSUMPTIONS | +$2,518 / +$2,731 at A09 = 0.5 transfer; transfer not measured |
| Manager lease replacements | **NOT JUSTIFIED** | Negative at every tested A10 within the horizon |
| Manager buy × 10 | NOT JUSTIFIED | $220,000 exceeds the budget |

**Defect found: the promotion stop rule cannot be carried out.** The Step 5 measurement plan reads: "cancel second weekend before its 14-day lead closes". Weekend 2 (Jul 25) must be ordered by about Jul 11, but weekend 1 (Jul 18–20) has not happened by then. The stop rule therefore can never fire as written.
- **Feasible alternatives:** commit to one weekend and decide on the second after measuring it (the second would then fall outside July), or accept both weekends as a single bet.
- **Not changed yet.** The disclosure is here; the Step 5 table needs your decision before it is edited.

## 5. What did the council contribute?

From the stored Step 5 ablation in `council_ablation_results`:
- **Optimizer alone:** finds no weaknesses (by construction).
- **Six agents with the Whisper Network:**
  - raised 3 independent objections;
  - retracted 1 causal claim;
  - flagged 2 decision-relevant fragilities, the A08 promotion dependence among them.
- **It did not change the recommended portfolio**, and on the manager's proposal it agreed with the analytic verdict 10/10.

The council's value is falsification and traceability, not new decisions. Its rules mirror the analytic rules, so its 10/10 agreement is a reproducibility check, not independent confirmation.

**Short-tenure rule:** not decision-relevant. M-5076 (49 days) has low per-hour theo, below the floor's first quartile, so the exposure rule never fired for any of the 10.

## 6. Which decision changes because the forecast exists?

Only one: the promotion choice in the **weak scenario**. All other decisions are the same with or without the model.
- With the past-only weekday baseline, the weakest event (Locals Week) is worth $3,521/day, below break-even ($5,281). The evidence portfolio is then **HOLD**.
- With the Holt-Winters counterfactual it is worth $11,729/day, above break-even. The portfolio then **keeps 2 promotions**.
- The base-case decision is the same under both methods.

**Caution: the model is weaker exactly where this decision uses it.** On the May–Jun holdout:

| Days | Holt-Winters vs baseline (MAE) | 80% interval coverage |
| --- | --- | --- |
| All days | 12.9% better | 0.61 |
| Non-event days | 18.2% better | n/a |
| Event days | **7.1% worse** | 0.40 |

The forecast's effect on the decision is therefore **INSUFFICIENT EVIDENCE**. It should not be used to override the weak-case HOLD.

**Records:**
- Results are stored in Delta. No MLflow model exists.
- Protocol hash: `939dfc9f…`.
- Stored local gates: 42/42 PASS. On Databricks, one gate (cross-environment MAE match) is recorded as FAIL.

## 7. What stays robust, and what is conditional

| Finding | Status |
| --- | --- |
| Do not replace the manager's 10 within July | ROBUST |
| M-1158 has a payout fault | ROBUST |
| Two of the 10 are already retired | ROBUST |
| Which of the 6 Back Forty machines are "not economic" vs "insufficient evidence" | CONDITIONAL (lease structure, ceiling) |
| Replacements after July | CONDITIONAL (unmeasured title effect; payback 48–76 days at A10 = 0.5) |
| Promotion weekends | CONDITIONAL (A08; break-even 5,281 vs weakest observed 5,016) |
| Forecast changing the weak-case decision | INSUFFICIENT EVIDENCE |

## 8. Changes made in this audit

- **Added:**
  - `scripts/run_audit.py`
  - `reports/audit/*.json`
  - this document
- **Not changed:** production code, tables, contracts and exports.
- **Not committed, pushed or deployed.**
