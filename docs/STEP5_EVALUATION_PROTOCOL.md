# Step 5 evaluation protocol (pre-registered)

Version: `step5-protocol-v1`. Frozen 2026-11-07 at 19:59 (Step 5 start), **before any Step 5 model was fitted or any holdout value was scored.** `scripts/run_step5.py` hashes this file (SHA-256) into every output row, and refuses to run if the hash changes after the protocol hash file is written.

## 1. Prediction target

Daily floor **theoretical win** (`property_day.theo_usd`, USD per gaming day, 06:00–06:00).

Deviation from `docs/MODELING_PLAN.md` (which proposed coin-in): the decision input this forecast informs, the promotion's excess theo per day (Step 3 assumption `A08`), is measured in theo. Theo is luck-free (expected win given bets), so the target matches the decision quantity. Coin-in and theo differ only by the hold mix. This deviation is recorded before training.

## 2–4. Issuance, horizon, decision date

- **Forecasting evaluation:** issued at the end of gaming date 2025-04-30 for every gaming day 2025-05-01 → 2025-06-30 (horizons 1–61), made once and frozen.
- **Decision use:** counterfactual (no-promotion) baselines for the two historical property promotions, each issued at the end of the day before the event starts, using only data up to then (horizon = event length). The decision date for the investment is 2025-07-01. The information cutoff is the end of 2025-06-30.

## 5–7. Business decision, catalog action, mapping

- **Action:** `A-PROMO` (property promotion weekend, $15,000 each, 2 weekends in the horizon).
- **Mapping:** Step 3 values one promotion weekend as `3 × A08 × contribution factor − $15,000`, where `A08` = excess theo per Fri–Sun promotion day. Excess = actual floor theo − **counterfactual forecast** of floor theo for that day. Step 3 estimated the counterfactual with a symmetric ±28-day same-weekday mean, which **uses days after the event** (not available at issuance). Step 5 re-estimates the counterfactual with past-only methods (baseline and candidate), recomputes `A08` (low, mean and high across the two events), and re-runs the **existing Step 3 optimiser**. All non-forecast assumptions stay fixed.
- **Causal status:** the excess is an observed association (2 events, no control group). A better counterfactual forecast improves the *measurement* of the association; it does not identify a causal promotion effect.

## 8–10. Periods

| Split | Gaming dates | Use |
| --- | --- | --- |
| Train | 2025-01-01 → 2025-03-31 (90 days) | Fit candidates for selection |
| Validation | 2025-04-01 → 2025-04-30 (30 days) | Choose the candidate setting; estimate residual quantiles for intervals |
| Final holdout | 2025-05-01 → 2025-06-30 (61 days) | Scored once, after refitting on Jan–Apr |

## 11–12. Methods

- **Baseline:** weekday mean, i.e. the mean target per weekday over the training window (Jan–Apr for the holdout). For event counterfactuals: the mean of the same weekday over the 4 prior non-event weeks.
- **Candidate:** Holt-Winters exponential smoothing (`statsmodels.tsa.holtwinters.ExponentialSmoothing`), additive weekly seasonality (period 7). The only tuning choice is trend ∈ {none, additive damped}, selected by validation MAE (April). Fitted by maximum likelihood on training data only.

## 13–14. Features and cutoff

Univariate: the target's own history up to the issuance date. No exogenous regressors. No same-day outcomes, weather, LVCVA, traffic or lags computed from forecast-period days.

## 15–16. Metrics

- **Primary:** holdout MAE (USD/day).
- **Secondary:** RMSE, bias (mean forecast − actual), WAPE, relative MAE improvement vs the baseline, MAE on event vs non-event days, and empirical 80% interval coverage.

## 17. Leakage restrictions (tested)

Chronological split only, with no random splits. The holdout is never used for fitting or selection. Event counterfactuals use data strictly before the event start. Interval quantiles come from validation residuals only.

## 18. Uncertainty

80% predictive interval = point forecast + 10th/90th percentiles of validation-period residuals (1–30 days ahead). Coverage is reported on the holdout. For decision use, the same residual quantiles bound the counterfactual (measurement uncertainty of the excess). The ordinary-weekend SD is **not** used as a causal confidence interval.

## 19. Financial decision comparison

Run the Step 3 optimiser (evidence-supported and conditional modes) with `A08` from: (a) the Step 3 original, (b) the baseline counterfactual, (c) the candidate counterfactual. Record portfolios, modeled contribution, and whether the $5,281/day break-even lies inside the measurement interval. Results are modeled contribution, not realised profit.

## 20. Council comparison

Recompute from the persisted Step 4 tables (no council rerun for configurations C and D). Configuration A = Step 3 optimiser only. Configuration B (single specialist) = each specialist alone through the same verifier and optimiser, if the code path supports it; otherwise BLOCKED. Count objections once per origin claim. Repeated deterministic runs are not independent trials.
