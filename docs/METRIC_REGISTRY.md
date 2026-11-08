# Metric registry

Generated from `analytics/metrics.py` (the single source of formulas) by `scripts/run_step1.py`. Do not edit by hand.

## Total coin-in (`coin_in`)

Sum of paid wagers, including replayed winnings.

- **Formula:** `SUM(coin_in_cents) / 100`
- **Source:** machine_day
- **Grain:** any aggregation of machine-days
- **Unit:** USD
- **Limitations:** Includes replayed winnings, so it exceeds cash put into machines.

## Total payout (`payout`)

Sum returned from game outcomes; jackpots counted once.

- **Formula:** `SUM(payout_cents) / 100`
- **Source:** machine_day
- **Grain:** any
- **Unit:** USD

## Total house win (`house_win`)

Coin-in minus payout (house gaming win).

- **Formula:** `SUM(house_win_cents) / 100  (== SUM(coin_in_cents - payout_cents) / 100)`
- **Source:** machine_day
- **Grain:** any
- **Unit:** USD
- **Assumptions:** Negative values are valid outcomes, never errors.

## Theoretical win (`theo`)

Expected house win given the bets actually made.

- **Formula:** `SUM(theo_cents) / 100, where theo = bet x (1 - configured_rtp)`
- **Source:** machine_day
- **Grain:** any
- **Unit:** USD
- **Limitations:** Exposure benchmark, not a guaranteed result. Assumes configured RTP is what the machine actually runs.

## Observed hold (`observed_hold`)

Share of coin-in kept by the house.

- **Formula:** `SUM(house_win_cents) / NULLIF(SUM(coin_in_cents), 0)`
- **Source:** machine_day
- **Grain:** any
- **Unit:** fraction
- **Assumptions:** Undefined (null) when coin-in is zero.
- **Limitations:** Never average daily holds; always a ratio of sums.

## Theoretical hold (`theo_hold`)

Expected share of coin-in kept by the house.

- **Formula:** `SUM(theo_cents) / NULLIF(SUM(coin_in_cents), 0)`
- **Source:** machine_day
- **Grain:** any
- **Unit:** fraction

## Luck residual (machine view) (`luck_residual`)

How much more (or less) the house won than expected.

- **Formula:** `house_win - theo`
- **Source:** machine_day
- **Grain:** any
- **Unit:** USD
- **Limitations:** Sign is opposite to the player-table residual (net + theo).

## Luck residual standard deviation (`luck_residual_sd`)

Standard deviation of house win around theo implied by the game math.

- **Formula:** `SQRT(SUM(sum_bet_squared x payout_multiplier_variance)) / 100`
- **Source:** machine_day + game_math
- **Grain:** any
- **Unit:** USD
- **Assumptions:** Spins are independent; per-spin payout variance from game_math applies.
- **Limitations:** Normal approximation is weak for very_high volatility games with few spins; use with caution for short windows.

## Luck z-score (`luck_z`)

Residual in units of its standard deviation.

- **Formula:** `luck_residual / luck_residual_sd`
- **Source:** machine_day + game_math
- **Grain:** any
- **Unit:** z
- **Assumptions:** |z| > ~3 is unlikely under pure luck; adjust for multiple comparisons.

## Observed hit rate (`hit_rate`)

Share of paid spins with a positive payout.

- **Formula:** `SUM(payout_positive_spins) / NULLIF(SUM(paid_spins), 0)`
- **Source:** machine_day
- **Grain:** any
- **Unit:** fraction
- **Limitations:** A hit can pay less than the wager.

## Hit-rate z-score vs configured (`hit_rate_z`)

Binomial test of observed hits against configured hit_probability.

- **Formula:** `(hits - spins x p) / SQRT(spins x p x (1 - p))`
- **Source:** machine_day + game_math
- **Grain:** machine x config
- **Unit:** z
- **Assumptions:** Spins independent; config constant within the group.
- **Limitations:** Detects payout-frequency anomalies, not payout-size anomalies.

## Scheduled machine hours (`scheduled_hours`)

Hours the machine was on the floor during gaming days.

- **Formula:** `SUM(scheduled_seconds) / 3600`
- **Source:** machine_day
- **Grain:** any
- **Unit:** hours
- **Assumptions:** Uses actual gaming-day length (82,800 s on 2025-03-08, DST).

## Available machine hours (`available_hours`)

Scheduled hours minus outage, repair, move and install downtime.

- **Formula:** `SUM(available_seconds) / 3600`
- **Source:** machine_day
- **Grain:** any
- **Unit:** hours

## Availability rate (`availability_rate`)

Share of scheduled time available.

- **Formula:** `SUM(available_seconds) / NULLIF(SUM(scheduled_seconds), 0)`
- **Source:** machine_day
- **Grain:** any
- **Unit:** fraction

## Downtime (`downtime_hours`)

Scheduled but unavailable hours.

- **Formula:** `(SUM(scheduled_seconds) - SUM(available_seconds)) / 3600`
- **Source:** machine_day
- **Grain:** any
- **Unit:** hours

## Win per available hour (`win_per_available_hour`)

House win normalised by exposure (time the machine could be played).

- **Formula:** `house_win / available_hours`
- **Source:** machine_day
- **Grain:** any
- **Unit:** USD/hour
- **Limitations:** Still contains luck; compare with theo_per_available_hour.

## Theo per available hour (`theo_per_available_hour`)

Luck-free demand per unit of exposure.

- **Formula:** `theo / available_hours`
- **Source:** machine_day
- **Grain:** any
- **Unit:** USD/hour
- **Limitations:** Reflects bet volume and configured RTP; location and game appeal are confounded.

## Carded player wagers (`carded_coin_in`)

Coin-in recorded to a loyalty card.

- **Formula:** `SUM(carded_coin_in_cents) / 100`
- **Source:** machine_day (or sessions)
- **Grain:** any
- **Unit:** USD
- **Limitations:** Tracked play only; never a substitute for all-play coin-in.

## Carded player payouts (`carded_payout`)

Payout on carded play.

- **Formula:** `SUM(carded_payout_cents) / 100`
- **Source:** machine_day (or sessions)
- **Grain:** any
- **Unit:** USD

## Tracked player gaming net (player view) (`player_net`)

What tracked players won (+) or lost (-).

- **Formula:** `carded_payout - carded_coin_in  (== -carded house win)`
- **Source:** player_period / sessions
- **Grain:** player x period
- **Unit:** USD
- **Limitations:** Label 'tracked'; uncarded play invisible at person level.

## Comp cost (economic) (`comp_cost`)

Cost to the house of redeemed comps.

- **Formula:** `SUM(fnb_transactions.cogs_cents WHERE comp_id IS NOT NULL) / 100  (== SUM(loyalty_ledger.economic_cost_cents) / 100)`
- **Source:** fnb_transactions / loyalty_ledger
- **Grain:** any
- **Unit:** USD
- **Assumptions:** Already inside POS cogs; subtract once.
- **Limitations:** Face value is menu price, not revenue and not cost.

## Comp reinvestment rate (`comp_reinvestment`)

Comp economic cost relative to theo for the same period.

- **Formula:** `comp_cost / NULLIF(theo, 0)`
- **Source:** property_day / player_period
- **Grain:** period
- **Unit:** fraction
- **Limitations:** Numerator is carded-guest comps, denominator is all-play theo unless carded theo is used; state which.

## Supplied machine operating costs (`supplied_machine_costs`)

Lease, service contract, power and direct repair costs from cost_rules.

- **Formula:** `lease + service + power + repair (prepared_daily_view)`
- **Source:** prepared_daily_view
- **Grain:** machine-day
- **Unit:** USD
- **Limitations:** Partial costs: no rent, tax, depreciation or full staffing.

## Contribution after supplied costs (`contribution_after_supplied_costs`)

House win minus supplied machine costs (machine) or plus POS margin minus all supplied costs (property).

- **Formula:** `house_win - supplied_machine_costs`
- **Source:** prepared_daily_view / property_day
- **Grain:** any
- **Unit:** USD
