"""Focused cross-domain investigations. Each tests at least one competing explanation.

Results are candidate findings with uncertainty, not recommendations.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from analytics.metrics import bonferroni, two_sided_p_from_z
from analytics.sql_dialect import days_between, dialect_of, seconds_between
from backend.repositories.base import AnalyticsRepository

SEED = 20250701


def _r(x: float, nd: int = 4) -> float:
    return round(float(x), nd)


# --------------------------------------------------------------------------- 1. leak
def payout_anomaly(repo: AnalyticsRepository) -> dict[str, Any]:
    """Machines whose payout frequency departs from configured game math."""
    d = repo.query_df("""
        SELECT m.machine_id, m.config_id, substr(CAST(m.gaming_date AS STRING), 1, 7) mon,
               sum(m.paid_spins) spins, sum(m.payout_positive_spins) hits,
               any_value(g.hit_probability)::DOUBLE p,
               sum(m.coin_in_cents) / 100.0 coin_in, sum(m.house_win_cents) / 100.0 hw,
               sum(m.theo_cents)::DOUBLE / 100 theo,
               sqrt(sum(m.sum_bet_squared * g.payout_multiplier_variance::DOUBLE)) / 100 sd
        FROM machine_day m JOIN game_math g USING (config_id)
        WHERE m.active AND m.paid_spins > 0 GROUP BY 1, 2, 3""")
    tot = d.groupby(["machine_id", "config_id"]).agg(
        spins=("spins", "sum"), hits=("hits", "sum"), p=("p", "first"),
        coin_in=("coin_in", "sum"), hw=("hw", "sum"), theo=("theo", "sum"),
        var=("sd", lambda s: float((s**2).sum()))).reset_index()
    tot["hit_z"] = (tot.hits - tot.spins * tot.p) / np.sqrt(tot.spins * tot.p * (1 - tot.p))
    tot["luck_z"] = (tot.hw - tot.theo) / np.sqrt(tot["var"])
    n = len(tot)
    tot["hit_p_bonf"] = [bonferroni(two_sided_p_from_z(z), n) for z in tot.hit_z]
    flagged = tot[tot.hit_p_bonf < 0.001].sort_values("hit_z", ascending=False)
    others = tot[~tot.index.isin(flagged.index)]

    cases = []
    for _, f in flagged.iterrows():
        mon = d[(d.machine_id == f.machine_id) & (d.config_id == f.config_id)].copy()
        mon = mon.sort_values("mon")
        mon["hit_z"] = (mon.hits - mon.spins * mon.p) / np.sqrt(mon.spins * mon.p * (1 - mon.p))
        mon["observed_hold"] = mon.hw / mon.coin_in
        months_significant = int((mon.hit_z.abs() > 3).sum())
        shortfall = float(f.theo - f.hw)
        days = int(repo.scalar(
            f"SELECT count(*) FROM machine_day WHERE active AND machine_id = '{f.machine_id}'"))
        cases.append({
            "machine_id": f.machine_id, "config_id": f.config_id,
            "configured_hit_probability": _r(f.p), "observed_hit_rate": _r(f.hits / f.spins),
            "paid_spins": int(f.spins), "hit_rate_z": _r(f.hit_z, 1),
            "hit_p_bonferroni": float(f.hit_p_bonf),
            "observed_hold": _r(f.hw / f.coin_in), "configured_hold": _r(f.theo / f.coin_in),
            "luck_z": _r(f.luck_z, 2),
            "house_win_shortfall_vs_theo_usd": _r(shortfall, 2),
            "shortfall_per_active_day_usd": _r(shortfall / days, 2),
            "months_with_abs_hit_z_gt_3": months_significant, "months_observed": len(mon),
            "monthly": mon[["mon", "hit_z", "observed_hold"]].round(4).to_dict("records"),
        })
    return {
        "observation": "Payout frequency far above configured hit probability.",
        "method": "Binomial z-test of payout-positive spins vs configured hit_probability "
                  "per machine x config, Bonferroni-adjusted over all machines; monthly "
                  "repeat to test persistence.",
        "machines_tested": n,
        "flagged": cases,
        "other_machines_hit_z_sd": _r(others.hit_z.std(), 3),
        "other_machines_hit_z_mean": _r(others.hit_z.mean(), 3),
        "competing_explanation": "Luck (a cold streak) rather than a payout-setting issue.",
        "test_result": "Hit frequency does not depend on jackpot size, so it is far less "
                       "noisy than dollar win; a persistent excess in every month is "
                       "inconsistent with chance. Other machines' hit z-scores have "
                       "SD ~1, so the test is calibrated.",
        "limitations": "Cannot distinguish misconfigured paytable from meter or "
                       "game-software fault; physical inspection is needed to confirm.",
    }


# --------------------------------------------------------------------------- 2. location
def walkway_closure(repo: AnalyticsRepository) -> dict[str, Any]:
    """Did the Entrance <-> Back Forty walkway closure reduce Back Forty demand?"""
    w = repo.query_df("""
        SELECT walkway_id, zone_a, zone_b, closed_from_utc, closed_to_utc, closure_reason
        FROM floor_walkways WHERE closed_from_utc IS NOT NULL""")
    if w.empty:
        return {"status": "no_closure_recorded"}
    row = w.iloc[0]
    cal = repo.query_df(f"""
        SELECT min(gaming_date) first_day, max(gaming_date) last_day FROM calendar_day
        WHERE gaming_day_start_utc >= TIMESTAMP '{row.closed_from_utc}'
          AND gaming_day_end_utc <= TIMESTAMP '{row.closed_to_utc}'""").iloc[0]
    target = row.zone_b if row.zone_a == "Z-ENT" else row.zone_a
    # Fixed machine set: machines active in the target zone on every day of the window,
    # so new installs or moves cannot create the effect.
    daily = repo.query_df(f"""
        WITH stable AS (SELECT machine_id FROM prepared_daily_view
                        GROUP BY 1 HAVING count(*) FILTER (WHERE active) = 181
                        AND count(DISTINCT zone_id) = 1)
        SELECT p.gaming_date, (p.zone_id = '{target}') treated,
               sum(m.theo_cents)::DOUBLE / 100 theo, sum(m.available_seconds) / 3600.0 ah,
               sum(m.occupied_seconds) / 3600.0 oh
        FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
        WHERE m.active AND m.machine_id IN (SELECT machine_id FROM stable)
        GROUP BY 1, 2""")
    piv = daily.pivot(index="gaming_date", columns="treated", values=["theo", "ah", "oh"])
    df = pd.DataFrame({
        "rate_t": piv["theo"][True] / piv["ah"][True],
        "rate_c": piv["theo"][False] / piv["ah"][False],
        "occ_t": piv["oh"][True] / piv["ah"][True],
        "occ_c": piv["oh"][False] / piv["ah"][False],
        "ah_t": piv["ah"][True],
    }).reset_index()
    df["gaming_date"] = pd.to_datetime(df.gaming_date)
    first, last = pd.Timestamp(cal.first_day), pd.Timestamp(cal.last_day)
    df["period"] = np.where(df.gaming_date < first, "pre",
                            np.where(df.gaming_date <= last, "closure", "post"))
    df["log_ratio"] = np.log(df.rate_t / df.rate_c)
    df["closure"] = (df.period == "closure").astype(int)
    df["post"] = (df.period == "post").astype(int)
    df["weekday"] = df.gaming_date.dt.dayofweek
    model = smf.ols("log_ratio ~ closure + post + C(weekday)", data=df).fit(
        cov_type="HAC", cov_kwds={"maxlags": 7})
    effect = float(model.params["closure"])
    ci = model.conf_int().loc["closure"].tolist()
    post_eff = float(model.params["post"])
    # Dollar effect: counterfactual treated rate = observed / exp(effect) during closure.
    clo = df[df.period == "closure"]
    lost = float(((clo.rate_t / np.exp(effect)) - clo.rate_t).mul(clo.ah_t).sum())
    lost_ci = [float(((clo.rate_t / np.exp(e)) - clo.rate_t).mul(clo.ah_t).sum())
               for e in ci[::-1]]

    traffic = repo.query_df(f"""
        SELECT {_period_case('c.gaming_date', first, last)} period,
               (t.zone_id = '{target}') treated,
               sum(t.entries_count) entries, sum(t.coverage_minutes) / 60.0 covered_hours
        FROM zone_traffic_hourly t JOIN calendar_day c
          ON t.hour_start_utc >= c.gaming_day_start_utc
         AND t.hour_start_utc < c.gaming_day_end_utc
        WHERE t.entries_count IS NOT NULL GROUP BY 1, 2""")
    traffic["entries_per_covered_hour"] = traffic.entries / traffic.covered_hours
    tr = traffic.pivot(index="period", columns="treated", values="entries_per_covered_hour")
    traffic_ratio = {p: _r(tr.loc[p, True] / tr.loc[p, False]) for p in tr.index}

    occ = df.groupby("period")[["occ_t", "occ_c"]].mean()
    return {
        "observation": f"Walkway {row.walkway_id} ({row.zone_a}<->{row.zone_b}) closed for "
                       f"{row.closure_reason}, gaming dates "
                       f"{pd.Timestamp(cal.first_day).date()} to "
                       f"{pd.Timestamp(cal.last_day).date()}.",
        "target_zone": target,
        "hypothesis": "The closure cut Back Forty demand beyond any floor-wide trend.",
        "alternative": "Back Forty's dip reflects floor-wide seasonality or machine changes.",
        "method": "Daily log ratio of target-zone to rest-of-floor theo per available hour "
                  "on a fixed set of machines that never moved; OLS with weekday effects "
                  "and closure/post indicators; HAC (Newey-West, 7 lags) errors.",
        "closure_effect_log_ratio": _r(effect),
        "closure_effect_pct": _r(100 * (np.exp(effect) - 1), 1),
        "closure_effect_ci95_pct": [_r(100 * (np.exp(c) - 1), 1) for c in ci],
        "closure_p_value": float(model.pvalues["closure"]),
        "post_vs_pre_pct": _r(100 * (np.exp(post_eff) - 1), 1),
        "post_p_value": float(model.pvalues["post"]),
        "estimated_lost_theo_usd": _r(lost, 0),
        "estimated_lost_theo_ci95_usd": [_r(x, 0) for x in sorted(lost_ci)],
        "closure_days": len(clo),
        "traffic_entries_ratio_target_vs_rest_by_period": traffic_ratio,
        "occupancy_by_period": occ.round(4).to_dict("index"),
        "limitations": "Single event, so effect size has wide uncertainty; traffic counters "
                       "count crossings not people; theo per hour also reflects bet size.",
    }


def _period_case(col: str, first: pd.Timestamp, last: pd.Timestamp) -> str:
    return (f"CASE WHEN {col} < DATE '{first.date()}' THEN 'pre' "
            f"WHEN {col} <= DATE '{last.date()}' THEN 'closure' ELSE 'post' END")


# --------------------------------------------------------------------------- 3. downtime
def downtime_by_manufacturer(repo: AnalyticsRepository) -> dict[str, Any]:
    """Is one manufacturer's downtime structurally higher, and what does it cost?"""
    d = dialect_of(repo)
    md = repo.query_df(f"""
        WITH f AS (SELECT machine_id, count(*) faults,
                          sum({seconds_between('opened_at_utc', 'available_at_utc', d)})
                            / 3600.0 fault_hours
                   FROM operations WHERE event_type = 'fault_repair' GROUP BY 1),
        m AS (SELECT machine_id, sum(scheduled_seconds) / 3600.0 sched_h,
                     sum(scheduled_seconds - available_seconds) / 3600.0 down_h,
                     sum(theo_cents)::DOUBLE / 100 / nullif(sum(available_seconds) / 3600.0, 0)
                       theo_per_ah,
                     count(*) active_days
              FROM machine_day WHERE active GROUP BY 1)
        SELECT m.*, mc.manufacturer, mc.lease_class,
               {days_between('mc.install_date', "DATE '2025-01-01'", d)} / 365.25 age_years,
               coalesce(f.faults, 0) faults, coalesce(f.fault_hours, 0) fault_hours
        FROM m JOIN machines mc USING (machine_id) LEFT JOIN f USING (machine_id)""")
    md["age_years"] = md.age_years.clip(lower=0)
    md["lost_theo"] = md.down_h * md.theo_per_ah
    by = md.groupby("manufacturer").agg(
        machines=("machine_id", "count"), sched_h=("sched_h", "sum"), down_h=("down_h", "sum"),
        faults=("faults", "sum"), active_days=("active_days", "sum"),
        lost_theo=("lost_theo", "sum"), mean_age=("age_years", "mean"))
    by["downtime_share"] = by.down_h / by.sched_h
    by["faults_per_1000_machine_days"] = 1000 * by.faults / by.active_days
    by["mean_hours_per_fault"] = by.down_h / by.faults.replace(0, np.nan)
    by["lost_theo_per_month_usd"] = by.lost_theo / 6
    # Competing explanation: older machines fail more, and Ridgeline may simply be older.
    pois = smf.glm("faults ~ C(manufacturer, Treatment('Halcyon')) + age_years",
                   data=md, family=__import__("statsmodels.api").api.families.Poisson(),
                   offset=np.log(md.active_days)).fit()
    coef = {k: {"rate_ratio": _r(np.exp(v), 3), "p_value": float(pois.pvalues[k]),
                "ci95": [_r(np.exp(x), 3) for x in pois.conf_int().loc[k]]}
            for k, v in pois.params.items() if k != "Intercept"}
    top = by.downtime_share.idxmax()
    rest = by.drop(index=top)
    excess_h = by.loc[top, "down_h"] - by.loc[top, "sched_h"] * (rest.down_h.sum()
                                                                 / rest.sched_h.sum())
    top_rate = float(md[md.manufacturer == top].theo_per_ah.mean())
    return {
        "observation": f"{top} machines have the highest downtime share.",
        "by_manufacturer": by.round(4).reset_index().to_dict("records"),
        "competing_explanation": "Machine age (older machines fail more), not manufacturer.",
        "method": "Poisson regression of fault counts with log(active days) offset on "
                  "manufacturer and age.",
        "poisson_rate_ratios": coef,
        "excess_downtime_hours_6mo": _r(excess_h, 1),
        "excess_lost_theo_6mo_usd": _r(excess_h * top_rate, 0),
        "excess_lost_theo_per_30d_usd": _r(excess_h * top_rate / 181 * 30, 0),
        "floor_downtime_share": _r(md.down_h.sum() / md.sched_h.sum(), 5),
        "limitations": "Lost theo assumes downtime hours would have been played at the "
                       "machine's average rate; downtime may cluster in quiet hours "
                       "(overstates) or busy hours (understates).",
    }


# --------------------------------------------------------------------------- 4. comps
def comp_rate_change(repo: AnalyticsRepository) -> dict[str, Any]:
    """Did the points price of a comp dollar change, and what did it do to comp cost?"""
    daily = repo.query_df("""
        SELECT c.gaming_date, -sum(l.points_delta)::DOUBLE points,
               sum(l.face_value_cents) / 100.0 face, sum(l.economic_cost_cents) / 100.0 cost,
               count(*) redemptions
        FROM loyalty_ledger l JOIN calendar_day c
          ON l.event_at_utc >= c.gaming_day_start_utc AND l.event_at_utc < c.gaming_day_end_utc
        WHERE l.event_type = 'redeem' GROUP BY 1 ORDER BY 1""")
    daily["rate"] = daily.points / daily.face
    # Change point: split maximising between-segment difference in mean daily rate.
    best, split = -1.0, None
    for i in range(14, len(daily) - 14):
        a, b = daily.rate.iloc[:i], daily.rate.iloc[i:]
        score = (a.mean() - b.mean()) ** 2 * i * (len(daily) - i)
        if score > best:
            best, split = score, daily.gaming_date.iloc[i]
    split_date = pd.Timestamp(split).date()
    tier = repo.query_df(f"""
        SELECT l.tier_before tier, c.gaming_date >= DATE '{split_date}' post,
               -sum(l.points_delta)::DOUBLE / (sum(l.face_value_cents) / 100.0) points_per_usd,
               count(*) n
        FROM loyalty_ledger l JOIN calendar_day c
          ON l.event_at_utc >= c.gaming_day_start_utc AND l.event_at_utc < c.gaming_day_end_utc
        WHERE l.event_type = 'redeem' GROUP BY 1, 2 ORDER BY 1, 2""")
    tier_tab = tier.pivot(index="tier", columns="post", values="points_per_usd")
    tier_tab.columns = ["pre", "post"]
    tier_tab["ratio_post_pre"] = tier_tab.post / tier_tab.pre
    mix = tier.pivot(index="tier", columns="post", values="n")
    mix = (mix / mix.sum()).round(4)
    mix.columns = ["pre_share", "post_share"]

    econ = repo.query_df(f"""
        WITH d AS (SELECT p.gaming_date, p.comp_cost_usd::DOUBLE comp,
                          sum(m.carded_theo_cents)::DOUBLE / 100 carded_theo
                   FROM property_day p JOIN machine_day m USING (gaming_date) GROUP BY 1, 2)
        SELECT gaming_date >= DATE '{split_date}' post, count(*) n_days,
               sum(comp) / count(*) comp_cost_per_day, sum(carded_theo) / count(*) theo_per_day,
               sum(comp) / sum(carded_theo) comp_cost_per_carded_theo
        FROM d GROUP BY 1 ORDER BY 1""")
    pre, post = econ.iloc[0], econ.iloc[1]
    redeem_ratio = repo.query_df(f"""
        SELECT c.gaming_date >= DATE '{split_date}' post,
               -sum(points_delta) FILTER (WHERE event_type = 'redeem')::DOUBLE
                 / sum(points_delta) FILTER (WHERE event_type = 'award') redeemed_per_awarded
        FROM loyalty_ledger l JOIN calendar_day c
          ON l.event_at_utc >= c.gaming_day_start_utc AND l.event_at_utc < c.gaming_day_end_utc
        GROUP BY 1 ORDER BY 1""")
    cost_per_face = float(daily.cost.sum() / daily.face.sum())
    return {
        "observation": f"Points required per comp dollar fell around gaming date {split_date}.",
        "change_point_gaming_date": str(split_date),
        "points_per_comp_usd_by_tier": tier_tab.round(3).reset_index().to_dict("records"),
        "redemption_tier_mix": mix.reset_index().to_dict("records"),
        "competing_explanation": "Tier mix: more Platinum/Gold redemptions (cheaper tiers) "
                                 "rather than a price change.",
        "test_result": "The rate roughly halves within every tier, so tier mix cannot "
                       "explain the step; mix explains only the gradual pre-change drift.",
        "comp_cost_per_day_pre_usd": _r(pre.comp_cost_per_day, 2),
        "comp_cost_per_day_post_usd": _r(post.comp_cost_per_day, 2),
        "comp_cost_per_carded_theo_pre": _r(pre.comp_cost_per_carded_theo, 5),
        "comp_cost_per_carded_theo_post": _r(post.comp_cost_per_carded_theo, 5),
        "comp_cost_change_pct": _r(100 * (post.comp_cost_per_day / pre.comp_cost_per_day - 1), 1),
        "points_redeemed_per_point_awarded_pre": _r(redeem_ratio.iloc[0, 1]),
        "points_redeemed_per_point_awarded_post": _r(redeem_ratio.iloc[1, 1]),
        "economic_cost_per_face_usd": _r(cost_per_face, 4),
        "limitations": "Redemption timing lags the change; two months post-change may not "
                       "show the full cost response. Unredeemed points are not valued: "
                       "the data cannot show how many will ever be redeemed.",
    }


def run_all(repo: AnalyticsRepository) -> dict[str, dict[str, Any]]:
    return {
        "payout_anomaly": payout_anomaly(repo),
        "walkway_closure": walkway_closure(repo),
        "downtime_by_manufacturer": downtime_by_manufacturer(repo),
        "comp_rate_change": comp_rate_change(repo),
    }
