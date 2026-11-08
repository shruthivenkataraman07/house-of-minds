# Modeling plan: daily floor coin-in

Status: **design and data preparation only. No model has been trained, and the holdout has not been scored.**

Code: [models/temporal_split.py](../models/temporal_split.py). Dataset: `data/processed/modeling_daily_floor.parquet`, built by `scripts/run_step1.py`.

## Decision it informs

How many technicians and floor staff to schedule each day in July, and which days a promotion weekend (A-PROMO, $15,000, 14-day lead) could fill. Both decisions are made in advance, so the forecast is also made in advance.

## Target and horizon

| Item | Choice |
| --- | --- |
| Target | `property_day.coin_in_usd`: all-play coin-in per gaming day (06:00–06:00) |
| Forecast origin | End of gaming date 2025-04-30 |
| Horizon | Every gaming day 2025-05-01 to 2025-06-30 (1–61 days ahead), made once and frozen |
| Why coin-in | Volume measure without payout luck. House win adds luck noise the business can't plan for |

## Does the data support it?

Yes. There are 181 complete gaming days with no missing target. Training-period mean daily coin-in is $1,384,919 (SD $267,242). Weekday is the dominant structure:

| Weekday | Training mean coin-in |
| --- | ---: |
| Tue | $1,112,942 |
| Wed | $1,149,981 |
| Mon | $1,212,138 |
| Thu | $1,290,980 |
| Sun | $1,465,879 |
| Fri | $1,655,737 |
| Sat | $1,820,595 |

## Temporal split

| Split | Gaming dates | Days | Use |
| --- | --- | ---: | --- |
| `train_inner` | 2025-01-01 to 2025-03-31 | 90 | Fit candidate models |
| `validation_inner` | 2025-04-01 to 2025-04-30 | 30 | Choose between candidates and settings |
| `holdout` | 2025-05-01 to 2025-06-30 | 61 | Scored **once**, after both forecasts are frozen |

After model selection, refit the chosen model on all of Jan–Apr, then forecast May–Jun. `assert_no_leakage()` fails if training and holdout overlap or if a disallowed feature is used. Tests: `tests/unit/test_temporal_split.py` and `tests/integration/test_data_foundation.py::test_temporal_split`.

## Features

Allowed (known at the origin): `weekday`, `is_weekend`, `federal_holiday`, `scheduled_hours` (DST day), `event_known`, and `active_machines_at_origin` (308).

| Feature | Leakage risk | Why it is excluded |
| --- | --- | --- |
| `event_any` | high | Includes events announced after the origin. 10 holdout days have an event, but only 3 (EDC) were announced by 2025-04-30. Locals Appreciation Week was announced 2025-05-26 |
| `lag_coin_in_7d_mean` and other `lag_*` | high | Fine for one-day-ahead forecasts, but inside a 61-day frozen forecast they use holdout actuals (GUIDE "Common issues") |
| `available_machine_hours` | high | Same-day outcome; downtime isn't known in advance |
| `tmax_c` (NOAA) | high | Observed weather; a real forecast would need a weather forecast |
| `city_visitors_month` (LVCVA) | high | Published after 2025 (`as_of_limitation`) |
| `total_zone_entries` | high | Same-day outcome correlated with the target |
| `active_machines` (daily) | low | Future installs weren't necessarily planned; use the origin-day count instead |

## Baselines (frozen before any holdout scoring)

1. **Constant mean:** mean daily coin-in over the training window (the guide's comparison baseline).
2. **Weekday mean:** mean daily coin-in per weekday over the training window (the guide's suggested simple model).

## Candidate model (Step 2)

One model only: a regression of log coin-in on weekday, holiday, known-event and DST indicators, plus a linear trend chosen on `validation_inner`. Advanced ML is optional and only kept if it beats the weekday baseline on `validation_inner`.

## Evaluation

- MAE in dollars, and MAE as a % of mean daily coin-in
- Bias (mean error); a forecast that is consistently high is a staffing cost
- MAE on known-event days vs other days
- Plot of predictions vs actuals for both baselines and the model
- Uncertainty: report the residual spread from `validation_inner` as an interval on daily forecasts

## Holdout discipline

- No feature selection, tuning or trend choice may look at May–June.
- Both baselines and the model are written to disk with a timestamp before the holdout is read.
- The holdout result is reported whether or not the model wins.

## Known risks

- Four months of training data cover one season; a trend fitted on Jan–Apr may extrapolate badly.
- The 2025-05-01 comp-rate change (see `reports/analytical_findings.md`) falls inside the holdout. If comps drive play, the holdout includes a regime change that no allowed feature represents. Report it as a limitation; don't patch it with holdout data.
- The Back Forty walkway closure (Mar 3–Apr 6) depresses training-period coin-in slightly. Optionally add an indicator for it, because the closure was known by the origin.
