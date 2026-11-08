"""Modeling preparation for daily floor coin-in (no training in this step).

Forecast design (GUIDE.md section 7): a forecast made as of the end of the training
period (2025-04-30) for every day of May-June, then compared with actuals. Because the
forecast is multi-day, any feature must be knowable on 2025-04-30: holdout outcomes and
lags computed from holdout days are leakage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from backend.repositories.base import AnalyticsRepository

TRAIN_START = date(2025, 1, 1)
INNER_TRAIN_END = date(2025, 3, 31)  # internal validation: fit Jan-Mar, score April
INNER_VALID_END = date(2025, 4, 30)
TRAIN_END = date(2025, 4, 30)  # forecast origin
HOLDOUT_START = date(2025, 5, 1)
HOLDOUT_END = date(2025, 6, 30)
TARGET = "coin_in_usd"


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    description: str
    known_at_origin: bool
    leakage_risk: str  # "none", "low", "high"
    note: str = ""


FEATURES: tuple[FeatureSpec, ...] = (
    FeatureSpec("weekday", "Day of week of the gaming date", True, "none"),
    FeatureSpec("is_weekend", "Saturday or Sunday", True, "none"),
    FeatureSpec("federal_holiday", "US federal holiday flag", True, "none"),
    FeatureSpec("scheduled_hours", "Gaming-day length (DST)", True, "none"),
    FeatureSpec("event_known", "Event active AND announced on or before the forecast origin",
                True, "low", "events.announced_date <= origin; later-announced events excluded"),
    FeatureSpec("event_any", "Any event active (ignores announcement date)", False, "high",
                "Uses events announced after the origin (e.g. Locals Week announced 2025-05-26)"),
    FeatureSpec("active_machines", "Machines on the floor that day", False, "low",
                "Holdout installs/retirements were not necessarily planned at the origin; "
                "use origin-day count instead"),
    FeatureSpec("active_machines_at_origin", "Machines on the floor on the origin date", True,
                "none"),
    FeatureSpec("lag_coin_in_7d_mean", "Mean coin-in over previous 7 days", False, "high",
                "Valid only for one-day-ahead forecasts; inside a multi-day holdout it uses "
                "holdout actuals"),
    FeatureSpec("available_machine_hours", "Same-day available hours", False, "high",
                "Same-day outcome; downtime is not known in advance"),
    FeatureSpec("tmax_c", "Same-day max temperature (NOAA)", False, "high",
                "Observed weather; a forecast would need a weather forecast"),
    FeatureSpec("city_visitors_month", "LVCVA monthly visitors", False, "high",
                "Published after 2025 (as_of_limitation); not knowable at origin"),
    FeatureSpec("total_zone_entries", "Same-day traffic counters", False, "high",
                "Same-day outcome correlated with the target"),
)

ALLOWED_FEATURES = [f.name for f in FEATURES if f.known_at_origin]
BASELINES = {
    "constant_mean": "Mean daily coin-in over the training period",
    "weekday_mean": "Mean daily coin-in per weekday over the training period",
}
METRICS = ["MAE (USD)", "MAE as % of mean daily coin-in", "bias (mean error, USD)",
           "MAE on event days vs non-event days"]


def build_daily_frame(repo: AnalyticsRepository, origin: date = TRAIN_END) -> pd.DataFrame:
    df = repo.query_df(f"""
        WITH ev AS (
          SELECT c.gaming_date,
                 count(e.event_id) > 0 event_any,
                 count(e.event_id) FILTER (WHERE e.announced_date <= DATE '{origin}') > 0
                   event_known
          FROM calendar_day c LEFT JOIN events e
            ON c.gaming_date BETWEEN e.start_date AND e.end_date
          GROUP BY 1)
        SELECT p.gaming_date, p.coin_in_usd::DOUBLE coin_in_usd, c.local_weekday weekday,
               c.is_weekend, c.federal_holiday IS NOT NULL federal_holiday,
               c.scheduled_seconds / 3600.0 scheduled_hours, ev.event_known, ev.event_any,
               p.active_machines,
               (SELECT active_machines FROM property_day WHERE gaming_date = DATE '{origin}')
                 active_machines_at_origin,
               p.available_machine_hours
        FROM property_day p JOIN calendar_day c USING (gaming_date) JOIN ev USING (gaming_date)
        ORDER BY 1""")
    df["gaming_date"] = pd.to_datetime(df.gaming_date).dt.date
    df["split"] = df.gaming_date.map(assign_split)
    return df


def assign_split(d: date) -> str:
    if d <= INNER_TRAIN_END:
        return "train_inner"
    if d <= INNER_VALID_END:
        return "validation_inner"
    if HOLDOUT_START <= d <= HOLDOUT_END:
        return "holdout"
    raise ValueError(f"{d} outside the modeling window")


def split_summary(df: pd.DataFrame) -> dict[str, dict[str, object]]:
    out = {}
    for s, g in df.groupby("split"):
        out[str(s)] = {"days": len(g), "first": str(g.gaming_date.min()),
                       "last": str(g.gaming_date.max()),
                       "mean_daily_coin_in_usd": round(float(g[TARGET].mean()), 2)}
    return out


def assert_no_leakage(df: pd.DataFrame, features: list[str]) -> None:
    """Raise if a feature is not knowable at the origin or splits overlap."""
    bad = [f for f in features if f not in ALLOWED_FEATURES]
    if bad:
        raise ValueError(f"features not available at forecast origin: {bad}")
    train_max = df.loc[df.split != "holdout", "gaming_date"].max()
    hold_min = df.loc[df.split == "holdout", "gaming_date"].min()
    if not train_max < hold_min:
        raise ValueError("training data overlaps the holdout")
