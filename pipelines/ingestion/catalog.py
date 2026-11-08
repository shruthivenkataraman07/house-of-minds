"""Registry of official Dashboard Royale tables.

Paths, grains and keys come from reference/DATA_DICTIONARY.md (release 0.9.0-draft).
Every downstream module refers to tables by `name`; only this file knows file paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Origin(StrEnum):
    SYNTHETIC = "synthetic"  # fictional casino world
    REAL_PUBLIC = "real_public"  # unmodified public sources (LVCVA, NOAA, Missouri)


@dataclass(frozen=True)
class TableSpec:
    name: str
    relative_path: str  # relative to the challenge data dir, without extension
    grain: str
    primary_key: tuple[str, ...]
    domain: str
    required: bool = True
    origin: Origin = Origin.SYNTHETIC
    money_unit: str = "none"  # "cents", "usd", "mixed" or "none"
    date_columns: tuple[str, ...] = field(default_factory=tuple)

    @property
    def parquet_path(self) -> str:
        return f"{self.relative_path}.parquet"


TABLES: tuple[TableSpec, ...] = (
    # 1. Prepared views
    TableSpec("prepared_daily_view", "1_prepared_views/prepared_daily_view",
              "machine x gaming date", ("machine_id", "gaming_date"), "machine",
              money_unit="usd", date_columns=("gaming_date",)),
    TableSpec("player_period", "1_prepared_views/player_period",
              "tracked player x month", ("player_id", "period_month"), "guest",
              money_unit="usd"),
    TableSpec("property_day", "1_prepared_views/property_day",
              "gaming date", ("gaming_date",), "demand",
              money_unit="usd", date_columns=("gaming_date",)),
    # 2. Machine decision
    TableSpec("calendar_day", "2_machine_decision/calendar_day", "gaming date",
              ("gaming_date",), "calendar", date_columns=("gaming_date",)),
    TableSpec("floor_locations", "2_machine_decision/floor_locations",
              "zone, bank, slot, outlet or entrance", ("location_id",), "floor"),
    TableSpec("floor_walkways", "2_machine_decision/floor_walkways",
              "walkway between zones", ("walkway_id",), "floor",
              date_columns=("closed_from_utc", "closed_to_utc")),
    TableSpec("machines", "2_machine_decision/machines", "machine", ("machine_id",),
              "machine", date_columns=("install_date", "retire_date")),
    TableSpec("game_math", "2_machine_decision/game_math", "game configuration",
              ("config_id",), "machine", money_unit="cents"),
    TableSpec("placements", "2_machine_decision/placements",
              "machine x location/config interval", ("placement_id",), "floor",
              date_columns=("effective_from_utc", "effective_to_utc")),
    TableSpec("machine_day", "2_machine_decision/machine_day", "machine x gaming date",
              ("machine_id", "gaming_date"), "machine", money_unit="cents",
              date_columns=("gaming_date",)),
    TableSpec("operations", "2_machine_decision/operations",
              "repair, move, install or retirement ticket", ("operation_id",), "operations",
              money_unit="cents", date_columns=("opened_at_utc", "available_at_utc")),
    TableSpec("cost_rules", "2_machine_decision/cost_rules", "supplied cost rule",
              ("cost_rule_id",), "finance", money_unit="mixed"),
    TableSpec("action_catalog", "2_machine_decision/action_catalog",
              "action the budget can buy", ("action_type_id",), "finance",
              money_unit="cents"),
    # 3. Guests (carded only, except fnb_transactions)
    TableSpec("players", "3_guests/players", "loyalty account", ("player_id",), "guest",
              date_columns=("enrolled_at_utc",)),
    TableSpec("sessions", "3_guests/sessions", "carded session segment",
              ("session_segment_id",), "guest", money_unit="cents",
              date_columns=("gaming_date",)),
    TableSpec("trips", "3_guests/trips", "observed property visit",
              ("observed_visit_id",), "guest", date_columns=("first_observed_at_utc",)),
    TableSpec("loyalty_ledger", "3_guests/loyalty_ledger", "points award or redemption",
              ("loyalty_event_id",), "comp", money_unit="cents",
              date_columns=("event_at_utc",)),
    TableSpec("fnb_transactions", "3_guests/fnb_transactions", "POS ticket",
              ("transaction_id",), "comp", money_unit="cents",
              date_columns=("event_at_utc",)),
    # 4. Context
    TableSpec("zone_traffic_hourly", "4_context/zone_traffic_hourly", "sensor x hour",
              ("sensor_id", "hour_start_utc"), "demand", date_columns=("hour_start_utc",)),
    TableSpec("events", "4_context/events", "event", ("event_id",), "demand",
              date_columns=("start_date", "end_date")),
    TableSpec("weather_daily", "4_context/real_sources/weather_daily", "calendar day",
              ("source_date",), "demand", origin=Origin.REAL_PUBLIC,
              date_columns=("source_date",)),
    TableSpec("city_visitation_monthly", "4_context/real_sources/city_visitation_monthly",
              "month", ("month",), "demand", origin=Origin.REAL_PUBLIC),
    TableSpec("benchmark_public", "4_context/real_sources/benchmark_public",
              "Missouri casino x slot category x month",
              ("property_id", "category", "month"), "benchmark", required=False,
              origin=Origin.REAL_PUBLIC, money_unit="usd"),
    TableSpec("benchmark_property_monthly",
              "4_context/real_sources/benchmark_property_monthly",
              "Missouri casino x month", ("property_id", "month"), "benchmark",
              required=False, origin=Origin.REAL_PUBLIC, money_unit="usd"),
    TableSpec("benchmark_state_monthly", "4_context/real_sources/benchmark_state_monthly",
              "month", ("month",), "benchmark", required=False,
              origin=Origin.REAL_PUBLIC, money_unit="usd"),
    TableSpec("visitor_profile_summary", "4_context/real_sources/visitor_profile_summary",
              "survey metric", ("metric_id", "segment"), "demand", required=False,
              origin=Origin.REAL_PUBLIC),
    TableSpec("visitor_profile_segments",
              "4_context/real_sources/visitor_profile_segments", "metric x segment",
              ("metric_id", "segment_group", "segment"), "demand", required=False,
              origin=Origin.REAL_PUBLIC),
    # 5. Optional
    TableSpec("machine_hour", "5_optional/machine_hour", "machine x hour",
              ("machine_id", "hour_start_utc"), "machine", required=False,
              money_unit="cents", date_columns=("gaming_date",)),
    TableSpec("security_incidents", "5_optional/security_incidents", "reported incident",
              ("incident_id",), "operations", required=False,
              date_columns=("occurred_at_utc",)),
    TableSpec("shift_roster", "5_optional/shift_roster", "staff assignment",
              ("assignment_id",), "operations", required=False,
              date_columns=("gaming_date",)),
    TableSpec("visitor_profile_monthly", "5_optional/visitor_profile_monthly",
              "fictional survey metric x month", ("month", "survey_metric"), "demand",
              required=False),
)

TABLES_BY_NAME: dict[str, TableSpec] = {t.name: t for t in TABLES}

# Documented foreign keys: (child_table, child_column, parent_table, parent_column)
FOREIGN_KEYS: tuple[tuple[str, str, str, str], ...] = (
    ("machine_day", "machine_id", "machines", "machine_id"),
    ("machine_day", "config_id", "game_math", "config_id"),
    ("machine_day", "location_id", "floor_locations", "location_id"),
    ("machine_day", "gaming_date", "calendar_day", "gaming_date"),
    ("prepared_daily_view", "machine_id", "machines", "machine_id"),
    ("placements", "machine_id", "machines", "machine_id"),
    ("placements", "location_id", "floor_locations", "location_id"),
    ("placements", "config_id", "game_math", "config_id"),
    ("operations", "machine_id", "machines", "machine_id"),
    ("operations", "location_id", "floor_locations", "location_id"),
    ("sessions", "machine_id", "machines", "machine_id"),
    ("sessions", "player_id", "players", "player_id"),
    ("sessions", "observed_visit_id", "trips", "observed_visit_id"),
    ("trips", "player_id", "players", "player_id"),
    ("loyalty_ledger", "player_id", "players", "player_id"),
    ("loyalty_ledger", "redeemed_pos_id", "fnb_transactions", "transaction_id"),
    ("loyalty_ledger", "source_segment_id", "sessions", "session_segment_id"),
    ("fnb_transactions", "player_id", "players", "player_id"),
    ("fnb_transactions", "comp_id", "loyalty_ledger", "loyalty_event_id"),
    ("player_period", "player_id", "players", "player_id"),
    ("zone_traffic_hourly", "zone_id", "floor_locations", "location_id"),
)
