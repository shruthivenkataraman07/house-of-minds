# Step 3 investment-input readiness

Checked 2026-11-07 against the official `action_catalog` and the evidence ledger. Nothing on this page was invented: where an input does not exist in the data, it is marked **missing**.

## Available (from official data)

| Input | Status | Source |
| --- | --- | --- |
| Action costs, including recurring cost over the horizon | Available, validated | `action_catalog`, `optimization/action_catalog.py` (guide's $3,380 lease example reproduced) |
| Evaluation horizon | Available | GUIDE: 30 days from 2025-07-01 |
| Lead times and operating days left in the horizon | Available | `lead_days` (A-REPLACE-BUY leaves 9 of 30 days; A-PROMO 16; A-INSPECT 29) |
| Quantity limits, ≤3 action types, budget can be kept | Available, tested | `price_selection` and its unit tests |
| Dependencies and incompatibilities | Available, tested | `same_machine` group (moves and replacements), `comp_policy` group (pilot vs change) |
| Downtime per unit (physical constraint) | Available | `downtime_minutes` |

## Evidence that can anchor benefit estimates (with uncertainty)

| Candidate action | Evidence | Size | Uncertainty |
| --- | --- | --- | --- |
| A-INSPECT on M-1158 ($1,200) | Payout-frequency anomaly | $199.81/active day shortfall vs theo | Cause (paytable vs meter) unverified; inspection outcome not guaranteed |
| A-WAYFINDING, Back Forty ($7,500) | Walkway closure cut zone demand | −31.2% during closure (95% CI −32.5% to −29.9%) | Shows access matters; uplift from **new** signage is not measured |
| A-PREVENTIVE, Ridgeline ($9,000) | Excess downtime vs other manufacturers | ~$5,072 theo per 30 days | Share of excess that maintenance would remove is unknown |
| A-COMP-PILOT / A-COMP-CHANGE | Comp points price halved 2025-05-01 | Comp cost per day +7.6% | No evidence yet that cheaper comps changed play |

## Missing (must be stated as assumptions in Step 3, with sensitivity ranges)

- **Uplift per action.** The catalog states "No uplift is promised", and no table measures the effect of any action.
- **Conversion from theo to contribution** for each action (lease share, service and power costs apply differently per machine).
- **Effect durations beyond July 30** (out of scope for the budget, but needed to justify capital purchases).
- **Measurement design details** (control groups, minimum detectable effect) for each funded action.
