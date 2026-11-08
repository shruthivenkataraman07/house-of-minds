"""Canonical outputs for official questions 2-5 (reusing Step 1 investigations).

Q2 demand, Q3 downtime, Q4 tracked players, Q5 loyalty comps. All money from integer-cent
sources or validated prepared views; ratios are ratio-of-sums; tracked (carded) results
are never mixed with all-play meters.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from analytics import investigations as INV
from backend.repositories.base import AnalyticsRepository


# --------------------------------------------------------------------------- Q2 demand
def floor_demand(repo: AnalyticsRepository) -> dict[str, Any]:
    monthly = repo.query_df("""
        SELECT p.month, count(*) FILTER (WHERE p.active) machine_days,
               sum(m.coin_in_cents) / 100.0 coin_in_usd,
               sum(m.theo_cents)::DOUBLE / 100 theo_usd,
               sum(m.available_seconds) / 3600.0 available_hours,
               (sum(m.coin_in_cents) / 100.0) / (sum(m.available_seconds) / 3600.0)
                 coin_in_per_available_hour,
               count(DISTINCT p.gaming_date) n_days
        FROM prepared_daily_view p JOIN machine_day m USING (machine_id, gaming_date)
        WHERE p.active GROUP BY 1 ORDER BY 1""")
    monthly["coin_in_per_day"] = monthly.coin_in_usd / monthly.n_days
    weekly = repo.query_df("""
        SELECT date_trunc('week', gaming_date) week_start, sum(coin_in_usd)::DOUBLE coin_in_usd,
               sum(theo_usd)::DOUBLE theo_usd, count(*) n_days,
               max(events_active) events
        FROM property_day GROUP BY 1 ORDER BY 1""")
    weekday = repo.query_df("""
        SELECT local_weekday weekday, avg(coin_in_usd)::DOUBLE avg_coin_in_usd, count(*) n_days
        FROM property_day GROUP BY 1""")
    zone = repo.query_df("""
        SELECT p.zone_id, p.month, sum(m.theo_cents)::DOUBLE / 100
                 / (sum(m.available_seconds) / 3600.0) theo_per_available_hour
        FROM prepared_daily_view p JOIN machine_day m USING (machine_id, gaming_date)
        WHERE p.active GROUP BY 1, 2 ORDER BY 1, 2""")
    traffic = repo.query_df("""
        SELECT t.zone_id, substr(CAST(c.gaming_date AS STRING), 1, 7) AS month,
               sum(t.entries_count)::DOUBLE / (sum(t.coverage_minutes) / 60.0)
                 entries_per_covered_hour,
               count(*) FILTER (WHERE t.entries_count IS NULL) offline_hours
        FROM zone_traffic_hourly t JOIN calendar_day c
          ON t.hour_start_utc >= c.gaming_day_start_utc AND t.hour_start_utc < c.gaming_day_end_utc
        GROUP BY 1, 2 ORDER BY 1, 2""")
    # Alternative explanation for the Jan-Apr -> May-Jun change: fewer machines vs lower
    # demand per machine. Compare total coin-in/day with coin-in per available hour.
    early = monthly[monthly.month <= "2025-04"]
    late = monthly[monthly.month >= "2025-05"]
    per_day_change = late.coin_in_usd.sum() / late.n_days.sum() / (
        early.coin_in_usd.sum() / early.n_days.sum()) - 1
    per_hour_change = (late.coin_in_usd.sum() / late.available_hours.sum()) / (
        early.coin_in_usd.sum() / early.available_hours.sum()) - 1
    closure = INV.walkway_closure(repo)
    tests = [
        {"change": "May-Jun vs Jan-Apr floor coin-in per day",
         "observed_pct": 100 * per_day_change,
         "alternative": "machine count / availability changed rather than demand",
         "test": "coin-in per available machine-hour",
         "result_pct": 100 * per_hour_change,
         "conclusion": (f"not explained by fewer machines: demand per available hour fell "
                        f"{-100 * per_hour_change:.1f}%, at least as much as the daily total "
                        f"({-100 * per_day_change:.1f}%)")
         if per_hour_change <= per_day_change else
         (f"partly exposure: per-hour demand changed {100 * per_hour_change:.1f}% vs "
          f"{100 * per_day_change:.1f}% for the daily total")},
        {"change": "Back Forty demand during walkway closure",
         "observed_pct": closure["closure_effect_pct"],
         "alternative": "floor-wide seasonality",
         "test": "difference vs rest of floor, fixed machines, weekday-adjusted (HAC)",
         "result_pct": closure["closure_effect_pct"],
         "conclusion": f"closure effect CI {closure['closure_effect_ci95_pct']}; recovered "
                       f"after reopening ({closure['post_vs_pre_pct']}%)"},
    ]
    return {"monthly": monthly, "weekly": weekly, "weekday": weekday, "zone_month": zone,
            "traffic_month": traffic, "explanations": pd.DataFrame(tests)}


# --------------------------------------------------------------------------- Q3 downtime
def downtime_economics(repo: AnalyticsRepository, contribution_factor: float
                       ) -> dict[str, Any]:
    rate = """WITH rate AS (SELECT machine_id, sum(theo_cents)::DOUBLE / 100
                 / nullif(sum(available_seconds) / 3600.0, 0) r
               FROM machine_day WHERE active GROUP BY 1)"""
    by = repo.query_df(f"""{rate}
        SELECT p.month, p.manufacturer, p.zone_id,
               sum(m.scheduled_seconds - m.available_seconds) / 3600.0 downtime_hours,
               sum(m.scheduled_seconds) / 3600.0 scheduled_hours,
               sum((m.scheduled_seconds - m.available_seconds) / 3600.0 * rate.r)
                 theo_at_risk_usd,
               sum(p.repair_cost_usd)::DOUBLE repair_cost_usd,
               sum(p.faults_opened)::BIGINT faults
        FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
        JOIN rate USING (machine_id) WHERE m.active GROUP BY 1, 2, 3""")
    by["contribution_at_risk_usd"] = by.theo_at_risk_usd * contribution_factor
    hour = repo.query_df(f"""{rate}
        SELECT h.local_hour, sum(3600 - h.available_seconds) / 3600.0 downtime_hours,
               sum((3600 - h.available_seconds) / 3600.0 * rate.r) theo_at_risk_usd
        FROM machine_hour h JOIN rate USING (machine_id)
        WHERE h.active GROUP BY 1 ORDER BY 1""")
    total = {"downtime_hours": float(by.downtime_hours.sum()),
             "scheduled_hours": float(by.scheduled_hours.sum()),
             "downtime_share": float(by.downtime_hours.sum() / by.scheduled_hours.sum()),
             "theo_at_risk_usd": float(by.theo_at_risk_usd.sum()),
             "contribution_at_risk_usd": float(by.contribution_at_risk_usd.sum()),
             "repair_cost_usd": float(by.repair_cost_usd.sum()),
             "label": "theoretical opportunity at risk, not guaranteed lost revenue"}
    return {"by_month_mfr_zone": by, "by_local_hour": hour, "total": total,
            "manufacturer_test": INV.downtime_by_manufacturer(repo)}


# --------------------------------------------------------------------------- Q4 players
def player_outcomes(repo: AnalyticsRepository) -> dict[str, Any]:
    p = repo.query_df("""
        SELECT player_id, any_value(opening_tier) tier,
               sum(tracked_coin_in_usd)::DOUBLE coin_in, sum(tracked_payout_usd)::DOUBLE payout,
               sum(tracked_net_usd)::DOUBLE net, sum(theo_usd)::DOUBLE theo
        FROM player_period GROUP BY 1""")
    played = p[p.coin_in > 0].copy()

    def top_share(col: str, frac: float) -> float:
        s = played[col].sort_values(ascending=False)
        k = max(1, int(np.ceil(len(s) * frac)))
        return float(s.iloc[:k].sum() / s.sum())

    loss = (-played.net).clip(lower=0)
    th = np.sort(played.theo.to_numpy())
    n = len(th)
    gini = float((2 * np.arange(1, n + 1) - n - 1).dot(th) / (n * th.sum()))
    carded = float(repo.scalar("SELECT sum(carded_coin_in_cents)::DOUBLE / sum(coin_in_cents) "
                               "FROM machine_day"))
    summary = {
        "players_with_tracked_play": int(len(played)), "players_in_ledger": int(len(p)),
        "tracked_coin_in_usd": float(played.coin_in.sum()),
        "tracked_payout_usd": float(played.payout.sum()),
        "tracked_player_net_usd": float(played.net.sum()),
        "tracked_theo_usd": float(played.theo.sum()),
        "share_players_ahead": float((played.net > 0).mean()),
        "top1pct_share_of_theo": top_share("theo", 0.01),
        "top10pct_share_of_theo": top_share("theo", 0.10),
        "top10pct_share_of_player_losses": float(loss.sort_values(ascending=False).iloc[
            : max(1, int(np.ceil(len(loss) * 0.1)))].sum() / loss.sum()),
        "gini_theo": gini, "carded_share_of_all_coin_in": carded,
        "coverage_limitation": "tracked (carded) play only; uncarded guests invisible",
    }
    by_tier = played.groupby("tier").agg(players=("player_id", "count"),
                                         coin_in=("coin_in", "sum"), net=("net", "sum"),
                                         theo=("theo", "sum")).reset_index()
    by_tier["share_ahead"] = played.groupby("tier").net.apply(lambda s: (s > 0).mean()).values
    return {"summary": summary, "by_tier": by_tier}


# --------------------------------------------------------------------------- Q5 comps
def loyalty_comps(repo: AnalyticsRepository) -> dict[str, Any]:
    monthly = repo.query_df("""
        SELECT substr(CAST(c.gaming_date AS STRING), 1, 7) AS month,
               sum(l.points_delta) FILTER (WHERE l.event_type = 'award')::BIGINT points_awarded,
               -sum(l.points_delta) FILTER (WHERE l.event_type = 'redeem')::BIGINT
                 points_redeemed,
               count(*) FILTER (WHERE l.event_type = 'redeem') redemptions,
               sum(l.face_value_cents) FILTER (WHERE l.event_type = 'redeem') / 100.0
                 comp_face_usd,
               sum(l.economic_cost_cents) FILTER (WHERE l.event_type = 'redeem') / 100.0
                 comp_cost_usd
        FROM loyalty_ledger l JOIN calendar_day c
          ON l.event_at_utc >= c.gaming_day_start_utc AND l.event_at_utc < c.gaming_day_end_utc
        GROUP BY 1 ORDER BY 1""")
    ct = repo.query_df("""SELECT substr(CAST(gaming_date AS STRING), 1, 7) AS month,
                                 sum(carded_theo_cents)::DOUBLE / 100 carded_theo_usd
                          FROM machine_day GROUP BY 1""")
    monthly = monthly.merge(ct, on="month")
    monthly["comp_cost_per_carded_theo"] = monthly.comp_cost_usd / monthly.carded_theo_usd
    monthly["points_per_comp_usd"] = monthly.points_redeemed / monthly.comp_face_usd
    return {"monthly": monthly, "change": INV.comp_rate_change(repo)}
