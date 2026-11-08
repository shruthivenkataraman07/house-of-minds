"""Central metric registry: the only place business formulas are defined.

Formulas follow reference/DATASET.md "Money definitions". Machine metrics are computed
from `machine_day` (integer cents, all play) and converted to dollars once, at the end.
Ratios are always ratio-of-sums. Off-floor machine-days (active = false) are excluded.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    name: str
    definition: str
    formula: str
    source: str
    grain: str
    unit: str
    assumptions: str = ""
    limitations: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        "coin_in", "Total coin-in", "Sum of paid wagers, including replayed winnings.",
        "SUM(coin_in_cents) / 100", "machine_day", "any aggregation of machine-days", "USD",
        limitations="Includes replayed winnings, so it exceeds cash put into machines."),
    MetricDefinition(
        "payout", "Total payout", "Sum returned from game outcomes; jackpots counted once.",
        "SUM(payout_cents) / 100", "machine_day", "any", "USD"),
    MetricDefinition(
        "house_win", "Total house win", "Coin-in minus payout (house gaming win).",
        "SUM(house_win_cents) / 100  (== SUM(coin_in_cents - payout_cents) / 100)",
        "machine_day", "any", "USD",
        assumptions="Negative values are valid outcomes, never errors."),
    MetricDefinition(
        "theo", "Theoretical win", "Expected house win given the bets actually made.",
        "SUM(theo_cents) / 100, where theo = bet x (1 - configured_rtp)", "machine_day",
        "any", "USD",
        limitations="Exposure benchmark, not a guaranteed result. Assumes configured RTP "
                    "is what the machine actually runs."),
    MetricDefinition(
        "observed_hold", "Observed hold", "Share of coin-in kept by the house.",
        "SUM(house_win_cents) / NULLIF(SUM(coin_in_cents), 0)", "machine_day", "any",
        "fraction", assumptions="Undefined (null) when coin-in is zero.",
        limitations="Never average daily holds; always a ratio of sums."),
    MetricDefinition(
        "theo_hold", "Theoretical hold", "Expected share of coin-in kept by the house.",
        "SUM(theo_cents) / NULLIF(SUM(coin_in_cents), 0)", "machine_day", "any", "fraction"),
    MetricDefinition(
        "luck_residual", "Luck residual (machine view)",
        "How much more (or less) the house won than expected.",
        "house_win - theo", "machine_day", "any", "USD",
        limitations="Sign is opposite to the player-table residual (net + theo)."),
    MetricDefinition(
        "luck_residual_sd", "Luck residual standard deviation",
        "Standard deviation of house win around theo implied by the game math.",
        "SQRT(SUM(sum_bet_squared x payout_multiplier_variance)) / 100",
        "machine_day + game_math", "any", "USD",
        assumptions="Spins are independent; per-spin payout variance from game_math applies.",
        limitations="Normal approximation is weak for very_high volatility games with few "
                    "spins; use with caution for short windows."),
    MetricDefinition(
        "luck_z", "Luck z-score", "Residual in units of its standard deviation.",
        "luck_residual / luck_residual_sd", "machine_day + game_math", "any", "z",
        assumptions="|z| > ~3 is unlikely under pure luck; adjust for multiple comparisons."),
    MetricDefinition(
        "hit_rate", "Observed hit rate", "Share of paid spins with a positive payout.",
        "SUM(payout_positive_spins) / NULLIF(SUM(paid_spins), 0)", "machine_day", "any",
        "fraction", limitations="A hit can pay less than the wager."),
    MetricDefinition(
        "hit_rate_z", "Hit-rate z-score vs configured",
        "Binomial test of observed hits against configured hit_probability.",
        "(hits - spins x p) / SQRT(spins x p x (1 - p))", "machine_day + game_math",
        "machine x config", "z",
        assumptions="Spins independent; config constant within the group.",
        limitations="Detects payout-frequency anomalies, not payout-size anomalies."),
    MetricDefinition(
        "scheduled_hours", "Scheduled machine hours",
        "Hours the machine was on the floor during gaming days.",
        "SUM(scheduled_seconds) / 3600", "machine_day", "any", "hours",
        assumptions="Uses actual gaming-day length (82,800 s on 2025-03-08, DST)."),
    MetricDefinition(
        "available_hours", "Available machine hours",
        "Scheduled hours minus outage, repair, move and install downtime.",
        "SUM(available_seconds) / 3600", "machine_day", "any", "hours"),
    MetricDefinition(
        "availability_rate", "Availability rate", "Share of scheduled time available.",
        "SUM(available_seconds) / NULLIF(SUM(scheduled_seconds), 0)", "machine_day", "any",
        "fraction"),
    MetricDefinition(
        "downtime_hours", "Downtime", "Scheduled but unavailable hours.",
        "(SUM(scheduled_seconds) - SUM(available_seconds)) / 3600", "machine_day", "any",
        "hours"),
    MetricDefinition(
        "win_per_available_hour", "Win per available hour",
        "House win normalised by exposure (time the machine could be played).",
        "house_win / available_hours", "machine_day", "any", "USD/hour",
        limitations="Still contains luck; compare with theo_per_available_hour."),
    MetricDefinition(
        "theo_per_available_hour", "Theo per available hour",
        "Luck-free demand per unit of exposure.",
        "theo / available_hours", "machine_day", "any", "USD/hour",
        limitations="Reflects bet volume and configured RTP; location and game appeal are "
                    "confounded."),
    MetricDefinition(
        "carded_coin_in", "Carded player wagers", "Coin-in recorded to a loyalty card.",
        "SUM(carded_coin_in_cents) / 100", "machine_day (or sessions)", "any", "USD",
        limitations="Tracked play only; never a substitute for all-play coin-in."),
    MetricDefinition(
        "carded_payout", "Carded player payouts", "Payout on carded play.",
        "SUM(carded_payout_cents) / 100", "machine_day (or sessions)", "any", "USD"),
    MetricDefinition(
        "player_net", "Tracked player gaming net (player view)",
        "What tracked players won (+) or lost (-).",
        "carded_payout - carded_coin_in  (== -carded house win)",
        "player_period / sessions", "player x period", "USD",
        limitations="Label 'tracked'; uncarded play invisible at person level."),
    MetricDefinition(
        "comp_cost", "Comp cost (economic)", "Cost to the house of redeemed comps.",
        "SUM(fnb_transactions.cogs_cents WHERE comp_id IS NOT NULL) / 100  "
        "(== SUM(loyalty_ledger.economic_cost_cents) / 100)",
        "fnb_transactions / loyalty_ledger", "any", "USD",
        assumptions="Already inside POS cogs; subtract once.",
        limitations="Face value is menu price, not revenue and not cost."),
    MetricDefinition(
        "comp_reinvestment", "Comp reinvestment rate",
        "Comp economic cost relative to theo for the same period.",
        "comp_cost / NULLIF(theo, 0)", "property_day / player_period", "period", "fraction",
        limitations="Numerator is carded-guest comps, denominator is all-play theo unless "
                    "carded theo is used; state which."),
    MetricDefinition(
        "supplied_machine_costs", "Supplied machine operating costs",
        "Lease, service contract, power and direct repair costs from cost_rules.",
        "lease + service + power + repair (prepared_daily_view)", "prepared_daily_view",
        "machine-day", "USD",
        limitations="Partial costs: no rent, tax, depreciation or full staffing."),
    MetricDefinition(
        "contribution_after_supplied_costs", "Contribution after supplied costs",
        "House win minus supplied machine costs (machine) or plus POS margin minus all "
        "supplied costs (property).",
        "house_win - supplied_machine_costs", "prepared_daily_view / property_day", "any",
        "USD"),
)

METRICS_BY_ID = {m.id: m for m in METRICS}


# SQL fragments over machine_day m JOIN game_math g. Inputs are cents and seconds.
MACHINE_AGGREGATES_SQL = """
    SUM(m.coin_in_cents) / 100.0                                   AS coin_in_usd,
    SUM(m.payout_cents) / 100.0                                    AS payout_usd,
    SUM(m.house_win_cents) / 100.0                                 AS house_win_usd,
    SUM(m.theo_cents)::DOUBLE / 100.0                              AS theo_usd,
    SUM(m.house_win_cents) / NULLIF(SUM(m.coin_in_cents), 0)::DOUBLE AS observed_hold,
    SUM(m.theo_cents)::DOUBLE / NULLIF(SUM(m.coin_in_cents), 0)    AS theo_hold,
    (SUM(m.house_win_cents) - SUM(m.theo_cents))::DOUBLE / 100.0   AS luck_residual_usd,
    SQRT(SUM(m.sum_bet_squared * g.payout_multiplier_variance::DOUBLE)) / 100.0
                                                                   AS luck_residual_sd_usd,
    SUM(m.paid_spins)                                              AS paid_spins,
    SUM(m.payout_positive_spins)                                   AS payout_positive_spins,
    SUM(m.scheduled_seconds) / 3600.0                              AS scheduled_hours,
    SUM(m.available_seconds) / 3600.0                              AS available_hours,
    (SUM(m.scheduled_seconds) - SUM(m.available_seconds)) / 3600.0 AS downtime_hours,
    SUM(m.available_seconds)::DOUBLE / NULLIF(SUM(m.scheduled_seconds), 0)
                                                                   AS availability_rate,
    SUM(m.carded_coin_in_cents) / 100.0                            AS carded_coin_in_usd,
    SUM(m.carded_payout_cents) / 100.0                             AS carded_payout_usd,
    SUM(m.carded_theo_cents)::DOUBLE / 100.0                       AS carded_theo_usd,
    COUNT(*)                                                       AS active_days
"""


def machine_metrics_sql(group_by: list[str], where: str = "TRUE") -> str:
    """Aggregate machine metrics at any grain; off-floor days always excluded."""
    keys = ", ".join(group_by)
    select_keys = f"{keys}," if keys else ""
    group = f"GROUP BY {keys}" if keys else ""
    return f"""
        SELECT {select_keys} {MACHINE_AGGREGATES_SQL}
        FROM machine_day m JOIN game_math g USING (config_id)
        WHERE m.active AND ({where})
        {group}
    """


def gaming_day_join(ts_utc_col: str, alias: str = "cal") -> str:
    """JOIN clause assigning a UTC timestamp to its gaming day (06:00-06:00 local, DST-safe).

    A range join (not a correlated subquery) so it runs on DuckDB and Databricks SQL.
    Timestamps outside the 181-day window drop out, as they belong to no gaming date.
    """
    return (f"JOIN calendar_day {alias} ON {ts_utc_col} >= {alias}.gaming_day_start_utc "
            f"AND {ts_utc_col} < {alias}.gaming_day_end_utc")


# ---- Pure-Python helpers (unit-tested; used where SQL is not convenient) -----------------

def ratio_of_sums(numerators: np.ndarray, denominators: np.ndarray) -> float | None:
    den = float(np.sum(denominators))
    return None if den == 0 else float(np.sum(numerators)) / den


def luck_z(house_win: float, theo: float, sd: float) -> float | None:
    return None if sd <= 0 else (house_win - theo) / sd


def hit_rate_z(hits: int, spins: int, p: float) -> float | None:
    if spins <= 0 or not 0 < p < 1:
        return None
    return (hits - spins * p) / math.sqrt(spins * p * (1 - p))


def two_sided_p_from_z(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def bonferroni(p: float, m: int) -> float:
    return min(1.0, p * m)
