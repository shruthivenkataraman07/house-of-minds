# Analytical methods

Every formula below is the one the code computes. Each comes with its symbols, the project's real numbers (from the validated snapshot `chf-v1:bc5e8ccc5d88a490`), the result, and what it means. The implementation and the test that checks it are named for each.

**Units:** dollars unless stated. **Period:** January 1 – June 30, 2025, which is 181 gaming days running 6 a.m. to 6 a.m. local time.

---

## 1. Casino money

**Casino win (house win)**

> W = C − P

- C is the amount wagered (coin-in).
- P is the prizes paid out.
- W is what the casino kept.

**Six-month floor:** $248,905,219.25 − $225,267,064.15 = **$23,638,155.10**

**Meaning:** what the casino actually kept. It moves with payout luck from day to day.

*Code:* `pipelines/validation/reconciliation.py` (check R01: 56,110 machine-days, 0 violations) · *Test:* `tests/integration`, `scripts/qa_parity.py`

**Share of wagers kept (hold)**

> hold = (Σ W) ÷ (Σ C) × 100%

Σ means "add up over every day in the period".

**Six-month floor:** $23,638,155 ÷ $248,905,219 × 100% = **9.50%**

**Meaning:** the casino kept about $9.50 of every $100 bet. Totals are added first and divided once (a ratio of sums), so a busy day counts more than a quiet one. Averaging daily percentages would give quiet days the same weight as busy ones.

**Expected casino win (theoretical win, "theo")**

> E = C × (1 − r)

- r is the game's designed payout rate (return to player, RTP).

**Example, machine M-1158:** $519,610 × (1 − 0.90) = **$51,961**

**Six-month floor:** **$23,545,364**

**Meaning:** what the games are built to keep on the amount bet. Luck cancels out, so this is the fairest measure of how much a machine was played.

*Check R08:* recomputed from `game_math` with a 0-cent difference on 55,092 active machine-days.

**Comp cost is counted once.** Loyalty rewards cost $190,669 (the point-of-sale cost of goods). Their menu value of $682,750 is a price, not a cost. Contribution subtracts the cost once and never subtracts it a second time (*check R10*).

## 2. Exposure: comparing machines fairly

> demand per available hour = (Σ C) ÷ (Σ A)

- A is the hours a machine was switched on and playable.

Available hours come from the machine's own meters: scheduled seconds minus downtime.

**Floor, six months:** $248,905,219 ÷ 1,316,887 h = **$189.01 per available machine-hour**

**Rules the pipeline enforces:**

- **Off-floor days:** 1,018 machine-days are excluded from every metric (*check R05*).
- **Location history:** machines that moved get their location from an interval join on `[effective_from, effective_to)`. A naive join on machine ID would overstate coin-in by **$3,255,941** (*check R07*).
- **Daylight saving:** one gaming day lasts 23 hours (82,800 seconds). Exposure uses scheduled seconds, so that day is not overstated by an hour (*check R13*).
- **Installs and retirements:** machines installed or retired mid-period are compared per available hour, never on totals.

## 3. Payout luck

**Luck score**

> z = (W − E) ÷ σ
>
> σ = √( Σᵢ bᵢ² × Var(mᵢ) )

- bᵢ is the bet on spin i.
- Var(mᵢ) is the variance of that game's payout multiplier, taken from its published paytable.
- σ is the size of a normal luck swing for this machine.

**M-1158:** ($15,796 − $51,961) ÷ $7,913 = **−4.57**

**Meaning:** M-1158 won $36,165 less than its games should have, which is 4.57 normal swings below expectation. Between −2 and +2 is ordinary luck; beyond ±3 is rare enough to investigate.

**Assumptions:** spins are independent and the paytable variance is correct. This is a large-sample normal approximation, not an exact distribution. A low z-score is evidence to investigate, not proof of a fault.

**Paying-spin test** (exact binomial)

> H ~ Binomial(n, p_g)
>
> adjusted p = min(1, 310 × p)

- H is the number of spins that paid anything.
- n is the number of spins played.
- p_g is the share of spins the game is designed to pay.
- 310 is the number of machines checked (Bonferroni correction for testing many machines).

**M-1158:** H ÷ n = 260,144 ÷ 674,454 = **38.57%** against a designed **31.54%**. The adjusted p is below 0.001.

**Meaning:** M-1158 pays out far more often than its game allows, which chance almost never produces. The finding is to inspect the meters and paytable; it does not mean replacing the machine.

*Code:* `analytics/diagnostics.py` · *Tests:* `tests/unit/test_diagnostics.py`.

## 4. Comparable machines and fair rank

> I = (Eᵢ ÷ Aᵢ) ÷ ( Σⱼ≠ᵢ Eⱼ ÷ Σⱼ≠ᵢ Aⱼ )

- Eᵢ ÷ Aᵢ is the machine's expected win per available hour.
- j ≠ i are its comparable machines: same game, same zone, leaving the machine itself out.

**M-1158:** I = **1.09** against 9 comparable machines

**Meaning:** M-1158 earns 9% more per hour than identical machines nearby. Leaving the machine out of its own benchmark stops it from pulling the comparison toward itself.

**Rank vs comparable machines:** 1 = weakest, 310 = strongest. M-1158 ranks **293 of 310**, although its total casino win ranks second-lowest.

## 5. Earnings gap breakdown

> W − W_ref = luck + exposure + location + game + machine
>
> luck = W − E · exposure = (A − Ā) × r̄ · location = (r_z − r̄) × A · game = (r_zg − r_z) × A · machine = (r − r_zg) × A

- W_ref = r̄ × Ā is a typical machine: the median hourly rate times the median hours.
- r_z is the zone's hourly rate, and r_zg is the rate for the same game in the same zone.

**M-1158:** −$36,165 (luck) + $181 (exposure) − $27,988 (location) − $2,623 (game) + $3,784 (machine) = **−$62,811**

**Meaning:** the parts add up exactly to the total; the stored reconciliation error is $0.00. They show *where* the gap sits, not *what caused it*, because location, game and guest mix overlap.

## 6. Ranking stability (Monte Carlo)

> Wᵏ = E + σ × εₖ, where εₖ ~ Normal(0, 1)
>
> P(lowest 10) = (number of replays with rank ≤ 10) ÷ 2,000

There are 2,000 replays with seed 20250701. In each replay only payout luck changes; play volume, bets and game maths stay fixed.

**M-1158:** in the lowest 10 in **1.4%** of replays (rank range 16 to 113)

**Meaning:** M-1158's place on the manager's list is mostly luck. This uses the same normal approximation as the luck score.

## 7. Natural experiment: the walkway closure

> ln( R_B40,d ÷ R_rest,d ) = α + β × closed_d + γ × after_d + weekday_d + ε_d
>
> effect = (e^β − 1) × 100%

- R is expected casino win per available hour, using only machines that never moved.
- B40 is Back Forty; "rest" is the rest of the floor on the same day.
- Errors are allowed to be correlated for up to 7 days (HAC standard errors).

**Result:** effect = **−31.2%** (95% range −32.5% to −29.9%) while the walkway was closed (March 3 – April 6, 2025). After it reopened the gap was −1.9%, so Back Forty recovered.

**Meaning:** comparing with the rest of the floor on the same days removes seasons and weekends. This is a strong association with a clear timeline, but it is not a randomized test.

*Code:* `analytics/investigations.py::walkway_closure`

## 8. Demand change

May–June compared with January–April:

- Wagered per day fell **2.1%**.
- Wagered per available hour fell **3.9%**.

**Meaning:** the drop is not explained by fewer machines being available, because demand per playable hour fell at least as much.

## 9. Downtime

> D = Σ (S − A)
>
> R = Σ (S − A) × r

- S is scheduled hours and A is available hours for each machine on each day.
- r is the machine's normal expected win per available hour.

**Result:** D = **5,021 hours** (floor availability 99.62%); R = **$90,313** of expected win at risk ($85,507 after revenue share and comps).

**Meaning:** an upper estimate. Some guests simply move to a nearby machine. Meter downtime reconciles to the operations tickets (*check R12*).

## 10. Tracked players and comps

**Scope:** only carded play, which is **65.8%** of all wagering. These figures are never scaled up to the whole floor.

**Players:**

- Tracked guests lost **$15,585,461** in total.
- **16.1%** finished ahead.
- The top 10% produced **63.8%** of tracked expected win.

**Concentration:**

> G = Σᵢ (2i − n − 1) x₍ᵢ₎ ÷ (n × Σᵢ xᵢ)

- x₍ᵢ₎ is the i-th smallest guest's expected win, and n is the number of tracked guests.

**Result:** **G = 0.71**, so play is heavily concentrated in a small group of guests.

**Comps:**

- Points per comp dollar = points redeemed ÷ menu value. It fell from **13.9** (January) to **5.7** (June) after the May 1 change, so rewards became about half as expensive in points.
- Cost ratio = comp cost ÷ tracked expected win. It rose from **1.11%** to **1.32%**.

**Meaning:** there was no comparison group, so we cannot tell whether the cheaper rewards brought in extra play.

## 11. Forecast validation

> MAE = Σ |yₜ − ŷₜ| ÷ n
>
> RMSE = √( Σ (yₜ − ŷₜ)² ÷ n )
>
> bias = Σ (ŷₜ − yₜ) ÷ n
>
> coverage = (days with Lₜ ≤ yₜ ≤ Uₜ) ÷ n

- yₜ is the actual daily expected casino win and ŷₜ is the forecast.
- [Lₜ, Uₜ] is the model's 80% range for day t.

**Setup:**

- **Target:** daily floor expected casino win.
- **Windows:** trained on January–March, model chosen on April, tested on the **May–June holdout (n = 61)**, which the model never saw.
- **Model:** Holt-Winters with additive weekly seasonality and a damped trend (statsmodels).
- **Baseline:** the average for each weekday in the training window.

| Measure | Holt-Winters | Weekday-mean baseline |
|---|---:|---:|
| MAE | **$5,552** | $6,699 |
| RMSE | $7,317 | $8,299 |
| Bias (forecast − actual) | +$1,459 | +$4,029 |
| 80% range coverage | 69% | — |

> improvement = (MAE_baseline − MAE_model) ÷ MAE_baseline = ($6,699 − $5,552) ÷ $6,699 = **17.1%**

**Where it fails:** on the 10 event days the model is **13.0% worse** than the baseline and its coverage falls to 30%. The 80% ranges are too narrow, which we disclose rather than hide.

**Decision link:** used as a past-only counterfactual, the forecast gives the promotion uplift used in the investment plan (assumption A08).

*Protocol:* `step5-protocol-v1` (SHA-256 recorded) · *Run:* `S5-4F2E08B4433A` · See [STEP5_EVALUATION_PROTOCOL.md](STEP5_EVALUATION_PROTOCOL.md).

## 12. Investment economics

**Promotion weekends**

> N = 2 × (3 × u × c − $15,000)
>
> break-even u* = $15,000 ÷ (3 × c)

- u is the extra expected win per promotion day.
- c ≈ 0.947 is the share kept after revenue share and comps.
- There are 3 days per weekend (Friday to Sunday).

**Calculation:**

- N = 2 × (3 × $16,237 × 0.947 − $15,000) = **$62,237**
- u* = $15,000 ÷ (3 × 0.947) = **$5,281 per day**

**Lease replacement**

> N = θ × (r* − r) × 24 × 16 × c − D − ($2,500 + $55 × 16)

- θ is the share of the gap a new title wins back (tested at 25%, 50% and 100%).
- r* is the zone's best hourly rate.
- 16 is the number of July operating days left after the 14-day lead time.
- D is the expected win lost during 6 hours of installation.

**Result:** none of the 68 floor-wide candidates pays back in the planning case. At 100% capture, 7 of the manager's 8 replaceable machines still lose money; the eighth, M-5076, would gain $20.

**Plan optimizer:** an exact mixed-integer program (SciPy MILP) chooses the plan.

> maximize Σ (qₐ × gₐ × c − qₐ × kₐ)

- qₐ is the quantity of action a, gₐ its modeled extra expected win and kₐ its catalog cost.
- **Constraints:** Σ qₐ × kₐ ≤ $100,000; at most 3 action types; catalog quantity limits and lead times.

*Code:* `optimization/investment_model.py`, `optimization/portfolio.py`.

## Limitations

- Promotion, inspection, machine-move and new-title effects are **not causally identified**. The promotion uplift comes from two past events with no control group.
- Luck scores and the replays use a normal approximation that assumes independent spins.
- The gap breakdown attributes; it does not establish cause.
- Player and comp results cover tracked (carded) play only.
- Modeled July figures are planning estimates, not booked profit.
- The forecast is unreliable on event days.
