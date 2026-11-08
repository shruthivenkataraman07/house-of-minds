"""Typed data contracts for the six analytical domains.

Consumers: analytical engines, FastAPI endpoints, the agent council, the evidence
ledger, the investment optimizer, the React dashboard and Phase 2 Databricks tables.
Row models define output schemas; ContractSpec documents inputs, grain and limits.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ContractSpec(BaseModel):
    domain: str
    output_table: str
    input_datasets: list[str]
    grain: str
    required_metrics: list[str]
    filters: list[str]
    validated_joins: list[str]
    limitations: list[str]
    evidence_ids: list[str] = Field(default_factory=list)


# ---- 1. Machine performance -------------------------------------------------------------
class MachinePerformanceRow(BaseModel):
    machine_id: str
    zone_id: str | None
    bank_id: str | None
    config_id: str | None
    manufacturer: str
    lease_class: str
    active_days: int
    available_hours: float
    availability_rate: float
    coin_in_usd: float
    house_win_usd: float
    theo_usd: float
    luck_residual_usd: float
    luck_z: float
    hit_rate_z_cfg: float | None
    win_per_available_hour: float
    theo_per_available_hour: float
    theo_per_ah_p05: float
    theo_per_ah_p95: float
    p_bottom_luck_aware: float
    gap_luck_usd: float
    gap_exposure_usd: float
    gap_location_usd: float
    gap_game_config_usd: float
    gap_machine_residual_usd: float
    rank_raw: int
    rank_exposure_adjusted: int
    rank_luck_aware: int
    rank_vs_peers: int
    explanation: str


# ---- 2. Casino demand -------------------------------------------------------------------
class DemandDayRow(BaseModel):
    gaming_date: date
    weekday: str
    events_active: str | None
    active_machines: int
    coin_in_usd: float
    house_win_usd: float
    theo_usd: float
    observed_hold: float | None
    available_machine_hours: float
    theo_per_available_hour: float
    total_zone_entries_observed: int | None
    counter_coverage_share: float


# ---- 3. Downtime and operations ---------------------------------------------------------
class DowntimeMonthRow(BaseModel):
    month: str
    manufacturer: str
    zone_id: str | None
    machine_days: int
    scheduled_hours: float
    downtime_hours: float
    downtime_share: float
    faults_opened: int
    lost_theo_usd: float = Field(description="downtime_hours x machine theo per available hour")
    repair_cost_usd: float


# ---- 4. Guest / player economics (tracked play only) ------------------------------------
class GuestEconomicsRow(BaseModel):
    period_month: str
    opening_tier: str
    players: int
    tracked_coin_in_usd: float
    tracked_payout_usd: float
    tracked_player_net_usd: float
    theo_usd: float
    luck_residual_usd: float
    tracked_contribution_usd: float
    top_10pct_share_of_theo: float
    share_of_players_ahead: float


# ---- 5. Comp economics ------------------------------------------------------------------
class CompDayRow(BaseModel):
    gaming_date: date
    redemptions: int
    points_redeemed: int
    comp_face_value_usd: float
    comp_cost_usd: float
    points_per_comp_usd: float | None
    carded_theo_usd: float
    comp_cost_per_carded_theo: float | None


# ---- 6. Financial intervention planning -------------------------------------------------
class InterventionOptionRow(BaseModel):
    action_type_id: str
    name: str
    unit: str
    eligible_target: str
    unit_cost_usd: float
    recurring_cost_usd_per_day: float
    lead_days: int
    operating_days_in_horizon: int
    unit_cost_in_horizon_usd: float
    downtime_minutes: int
    quantity_limit: int
    incompatibility_group: str | None
    max_spend_usd: float
    notes: str | None


CONTRACTS: tuple[ContractSpec, ...] = (
    ContractSpec(
        domain="machine_performance", output_table="contract_machine_performance",
        input_datasets=["machine_day", "game_math", "prepared_daily_view", "machines"],
        grain="machine (Jan 1 - Jun 30, 2025, active days only)",
        required_metrics=["house_win", "theo", "luck_residual", "luck_z", "hit_rate_z",
                          "available_hours", "win_per_available_hour",
                          "theo_per_available_hour"],
        filters=["zone_id", "manufacturer", "config_id", "lease_class", "explanation tag"],
        validated_joins=["machine_day x game_math on config_id (R08)",
                         "machine_day x prepared_daily_view on (machine_id, gaming_date) (R02)"],
        limitations=["Rankings describe exposure-adjusted, luck-free demand, not proof of "
                     "machine quality", "Back Forty values include the Mar 3-Apr 6 "
                     "walkway closure", "Bootstrap interval covers day-to-day variation only"]),
    ContractSpec(
        domain="casino_demand", output_table="contract_demand_day",
        input_datasets=["property_day", "calendar_day"], grain="gaming date",
        required_metrics=["coin_in", "house_win", "theo", "observed_hold",
                          "theo_per_available_hour"],
        filters=["date range", "weekday", "event"],
        validated_joins=["property_day == sum(machine_day) (R03)"],
        limitations=["Traffic entries are sensor crossings, not people; offline hours are "
                     "missing, not zero"]),
    ContractSpec(
        domain="downtime_operations", output_table="contract_downtime_month",
        input_datasets=["machine_day", "prepared_daily_view", "operations"],
        grain="month x manufacturer x zone",
        required_metrics=["scheduled_hours", "downtime_hours", "availability_rate",
                          "lost theo (estimate)", "repair cost"],
        filters=["month", "manufacturer", "zone_id"],
        validated_joins=["meter downtime == ticket outage hours (R12)",
                         "repair cost == operations.direct_cost_cents (R11)"],
        limitations=["Lost theo assumes downtime would be played at the machine's "
                     "average rate"]),
    ContractSpec(
        domain="guest_economics", output_table="contract_guest_month",
        input_datasets=["player_period"], grain="month x opening tier (tracked players)",
        required_metrics=["tracked coin-in", "tracked payout", "player net", "theo",
                          "concentration", "share of players ahead"],
        filters=["month", "opening_tier"],
        validated_joins=["player_period == sessions == machine_day carded (R09)"],
        limitations=["Carded play is 65.8% of coin-in; uncarded guests invisible",
                     "Player sign convention: net = payout - coin-in"]),
    ContractSpec(
        domain="comp_economics", output_table="contract_comp_day",
        input_datasets=["loyalty_ledger", "property_day", "machine_day", "calendar_day"],
        grain="gaming date",
        required_metrics=["comp_cost", "comp face value", "points per comp dollar",
                          "comp cost per carded theo"],
        filters=["date range", "pre/post 2025-05-01 policy change"],
        validated_joins=["ledger economic cost == linked POS cogs (R10)",
                         "ledger events mapped to gaming dates via calendar_day (R13)"],
        limitations=["Face value is menu price, not cost or revenue",
                     "Comp cost is inside POS cogs; never subtract twice"]),
    ContractSpec(
        domain="intervention_planning", output_table="contract_intervention_options",
        input_datasets=["action_catalog", "cost_rules"],
        grain="action type", required_metrics=["cost in 30-day horizon", "lead time",
                                               "quantity limit", "downtime"],
        filters=["action_type_id", "incompatibility_group"],
        validated_joins=["none (reference table)"],
        limitations=["Catalog gives prices, not effects; benefits must be estimated with "
                     "uncertainty"]),
)
