"""Builders for the six domain contract tables. Each row is validated by its schema."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from pydantic import BaseModel

from analytics.machine_performance import ComparisonResult
from backend.repositories.base import AnalyticsRepository
from backend.schemas.contracts import (
    CompDayRow,
    DemandDayRow,
    DowntimeMonthRow,
    GuestEconomicsRow,
    InterventionOptionRow,
    MachinePerformanceRow,
)
from optimization.action_catalog import ActionCatalog


def validate_rows(df: pd.DataFrame, model: type[BaseModel]) -> pd.DataFrame:
    """Validate every row against the schema and return only schema columns."""
    cols = list(model.model_fields)
    clean = df[cols].replace({np.nan: None})
    for rec in clean.to_dict("records"):
        model.model_validate(rec)
    return df[cols]


def machine_performance(cmp: ComparisonResult) -> pd.DataFrame:
    return validate_rows(cmp.machines, MachinePerformanceRow)


def casino_demand(repo: AnalyticsRepository) -> pd.DataFrame:
    df = repo.query_df("""
        SELECT gaming_date, local_weekday weekday, events_active, active_machines,
               coin_in_usd::DOUBLE coin_in_usd, house_win_usd::DOUBLE house_win_usd,
               theo_usd::DOUBLE theo_usd, observed_hold, available_machine_hours,
               theo_usd::DOUBLE / available_machine_hours theo_per_available_hour,
               total_zone_entries_observed, counter_coverage_share
        FROM property_day ORDER BY 1""")
    return validate_rows(df, DemandDayRow)


def downtime_operations(repo: AnalyticsRepository) -> pd.DataFrame:
    df = repo.query_df("""
        WITH rate AS (SELECT machine_id, sum(theo_cents)::DOUBLE / 100
                        / nullif(sum(available_seconds) / 3600.0, 0) r
                      FROM machine_day WHERE active GROUP BY 1)
        SELECT p.month, p.manufacturer, p.zone_id, count(*) machine_days,
               sum(m.scheduled_seconds) / 3600.0 scheduled_hours,
               sum(m.scheduled_seconds - m.available_seconds) / 3600.0 downtime_hours,
               sum(m.scheduled_seconds - m.available_seconds)::DOUBLE
                 / sum(m.scheduled_seconds) downtime_share,
               sum(p.faults_opened)::BIGINT faults_opened,
               sum((m.scheduled_seconds - m.available_seconds) / 3600.0 * coalesce(rate.r, 0))
                 lost_theo_usd,
               sum(p.repair_cost_usd)::DOUBLE repair_cost_usd
        FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
        LEFT JOIN rate USING (machine_id)
        WHERE m.active GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""")
    return validate_rows(df, DowntimeMonthRow)


def guest_economics(repo: AnalyticsRepository) -> pd.DataFrame:
    df = repo.query_df("""
        WITH r AS (SELECT *, percent_rank() OVER (PARTITION BY period_month, opening_tier
                                                  ORDER BY theo_usd DESC) pr
                   FROM player_period)
        SELECT period_month, opening_tier, count(*) players,
               sum(tracked_coin_in_usd)::DOUBLE tracked_coin_in_usd,
               sum(tracked_payout_usd)::DOUBLE tracked_payout_usd,
               sum(tracked_net_usd)::DOUBLE tracked_player_net_usd,
               sum(theo_usd)::DOUBLE theo_usd, sum(luck_residual_usd)::DOUBLE luck_residual_usd,
               sum(tracked_contribution_usd)::DOUBLE tracked_contribution_usd,
               (sum(theo_usd) FILTER (WHERE pr < 0.1) / nullif(sum(theo_usd), 0))::DOUBLE
                 top_10pct_share_of_theo,
               (count(*) FILTER (WHERE tracked_net_usd > 0))::DOUBLE / count(*)
                 share_of_players_ahead
        FROM r GROUP BY 1, 2 ORDER BY 1, 2""")
    df["top_10pct_share_of_theo"] = df.top_10pct_share_of_theo.fillna(0.0)
    return validate_rows(df, GuestEconomicsRow)


def comp_economics(repo: AnalyticsRepository) -> pd.DataFrame:
    df = repo.query_df("""
        WITH l AS (SELECT c.gaming_date, count(*) redemptions,
                          -sum(l.points_delta) points_redeemed
                   FROM loyalty_ledger l JOIN calendar_day c
                     ON l.event_at_utc >= c.gaming_day_start_utc
                    AND l.event_at_utc < c.gaming_day_end_utc
                   WHERE l.event_type = 'redeem' GROUP BY 1),
        t AS (SELECT gaming_date, sum(carded_theo_cents)::DOUBLE / 100 carded_theo_usd
              FROM machine_day GROUP BY 1)
        SELECT p.gaming_date, coalesce(l.redemptions, 0) redemptions,
               coalesce(l.points_redeemed, 0)::BIGINT points_redeemed,
               p.comp_face_value_usd::DOUBLE comp_face_value_usd,
               p.comp_cost_usd::DOUBLE comp_cost_usd,
               l.points_redeemed::DOUBLE / nullif(p.comp_face_value_usd, 0) points_per_comp_usd,
               t.carded_theo_usd,
               p.comp_cost_usd::DOUBLE / nullif(t.carded_theo_usd, 0) comp_cost_per_carded_theo
        FROM property_day p LEFT JOIN l USING (gaming_date) JOIN t USING (gaming_date)
        ORDER BY 1""")
    return validate_rows(df, CompDayRow)


def intervention_planning(catalog: ActionCatalog) -> pd.DataFrame:
    rows = []
    for a in catalog.actions.values():
        rows.append({
            "action_type_id": a.action_type_id, "name": a.name, "unit": a.unit,
            "eligible_target": a.eligible_target, "unit_cost_usd": a.unit_cost_cents / 100,
            "recurring_cost_usd_per_day": a.recurring_cost_cents_per_day / 100,
            "lead_days": a.lead_days, "operating_days_in_horizon": a.operating_days,
            "unit_cost_in_horizon_usd": a.unit_cost_in_horizon_cents() / 100,
            "downtime_minutes": a.downtime_minutes, "quantity_limit": a.quantity_limit,
            "incompatibility_group": a.incompatibility_group,
            "max_spend_usd": a.quantity_limit * a.unit_cost_in_horizon_cents() / 100,
            "notes": a.notes,
        })
    return validate_rows(pd.DataFrame(rows), InterventionOptionRow)


BUILDERS: dict[str, Callable[..., pd.DataFrame]] = {
    "casino_demand": casino_demand,
    "downtime_operations": downtime_operations,
    "guest_economics": guest_economics,
    "comp_economics": comp_economics,
}
