"""Fair machine comparisons: raw vs exposure-adjusted vs luck-aware rankings.

Shortfall decomposition (exact, additive) against a reference "typical machine"
(floor-median theo per available hour x floor-median available hours):

    house_win - reference = luck + exposure + location + game_config + machine_residual
      luck             = house_win - theo
      exposure         = (available_hours - ref_hours) x ref_rate
      location         = (zone_rate - ref_rate) x available_hours
      game_config      = (peer_rate - zone_rate) x available_hours
      machine_residual = (machine_rate - peer_rate) x available_hours
    where rate = theo per available hour and peer_rate = same config in the same zone.

Adjusted rankings describe exposure and luck-free demand. They are not proof of
machine quality: location, game configuration and player mix remain confounded.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from analytics.metrics import bonferroni, machine_metrics_sql, two_sided_p_from_z
from backend.repositories.base import AnalyticsRepository

BOTTOM_N = 10
BOOTSTRAP_DRAWS = 1000
SEED = 20250701


def machine_table(repo: AnalyticsRepository, where: str = "TRUE") -> pd.DataFrame:
    """One row per machine with metrics, attributes, luck and hit-rate tests."""
    df = repo.query_df(machine_metrics_sql(["m.machine_id"], where))
    attrs = repo.query_df(f"""
        WITH z AS (
          SELECT machine_id, zone_id, bank_id, zone_name, d,
                 row_number() OVER (PARTITION BY machine_id ORDER BY d DESC, zone_id) rk
          FROM (SELECT p.machine_id, p.zone_id, p.bank_id, p.zone_name, count(*) d
                FROM prepared_daily_view p JOIN machine_day m USING (machine_id, gaming_date)
                WHERE p.active AND ({where}) GROUP BY 1, 2, 3, 4))
        , cfg AS (
          SELECT machine_id, count(DISTINCT location_id) n_locations,
                 count(DISTINCT config_id) n_configs, min(config_id) config_ids
          FROM machine_day WHERE active GROUP BY 1)
        SELECT mc.machine_id, mc.manufacturer, mc.theme, mc.lease_class, mc.install_date,
               mc.retire_date, z.zone_id, z.zone_name, z.bank_id,
               cfg.n_locations, cfg.n_configs, cfg.config_ids
        FROM machines mc LEFT JOIN z ON z.machine_id = mc.machine_id AND z.rk = 1
        LEFT JOIN cfg ON cfg.machine_id = mc.machine_id""")
    hits = repo.query_df(f"""
        SELECT m.machine_id, m.config_id, g.volatility_class, g.configured_rtp::DOUBLE rtp,
               sum(m.paid_spins) spins, sum(m.payout_positive_spins) hits,
               any_value(g.hit_probability)::DOUBLE p
        FROM machine_day m JOIN game_math g USING (config_id)
        WHERE m.active AND ({where}) GROUP BY 1, 2, 3, 4""")
    hits["hit_rate_z_cfg"] = (hits.hits - hits.spins * hits.p) / np.sqrt(
        hits.spins * hits.p * (1 - hits.p))
    # Most extreme configuration per machine (machines rarely change config).
    hits = hits.loc[hits.groupby("machine_id").hit_rate_z_cfg.apply(
        lambda s: s.abs().idxmax())]
    hits = hits.rename(columns={"spins": "spins_cfg"})[
        ["machine_id", "volatility_class", "rtp", "hit_rate_z_cfg", "hits", "spins_cfg", "p"]]

    out = df.merge(attrs, on="machine_id", how="left").merge(hits, on="machine_id", how="left")
    # Deterministic order regardless of engine: downstream bootstrap draws depend on it.
    out = out.sort_values("machine_id").reset_index(drop=True)
    out["luck_z"] = out.luck_residual_usd / out.luck_residual_sd_usd
    out["win_per_available_hour"] = out.house_win_usd / out.available_hours
    out["theo_per_available_hour"] = out.theo_usd / out.available_hours
    out["observed_hit_rate"] = out.payout_positive_spins / out.paid_spins
    n = len(out)
    out["luck_p_bonferroni"] = [bonferroni(two_sided_p_from_z(z), n) for z in out.luck_z]
    out["hit_p_bonferroni"] = [bonferroni(two_sided_p_from_z(z), n)
                               for z in out.hit_rate_z_cfg.fillna(0)]
    return out


def peer_rates(repo: AnalyticsRepository) -> pd.DataFrame:
    """Theo per available hour for each (zone, game configuration) cell."""
    return repo.query_df("""
        SELECT p.zone_id, m.config_id, count(DISTINCT m.machine_id) peer_machines,
               sum(m.theo_cents)::DOUBLE / 100 / (sum(m.available_seconds) / 3600.0)
                 peer_theo_per_available_hour
        FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
        WHERE m.active GROUP BY 1, 2""")


def zone_rates(repo: AnalyticsRepository, where: str = "TRUE") -> pd.DataFrame:
    """Zone theo per available hour using each machine-day's own zone (moves respected)."""
    return repo.query_df(f"""
        SELECT p.zone_id, any_value(p.zone_name) zone_name,
               count(DISTINCT p.machine_id) machines,
               sum(m.theo_cents)::DOUBLE / 100 / (sum(m.available_seconds) / 3600.0)
                 zone_theo_per_available_hour,
               sum(m.house_win_cents) / 100.0 / (sum(m.available_seconds) / 3600.0)
                 zone_win_per_available_hour
        FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
        WHERE m.active AND ({where}) GROUP BY 1 ORDER BY 4""")


@dataclass
class ComparisonResult:
    machines: pd.DataFrame
    zones: pd.DataFrame
    reference_rate: float
    reference_hours: float
    rank_changes: pd.DataFrame


def compare_machines(repo: AnalyticsRepository) -> ComparisonResult:
    m = machine_table(repo)
    z = zone_rates(repo)
    m = m.merge(z[["zone_id", "zone_theo_per_available_hour"]], on="zone_id", how="left")
    m["config_id"] = m.config_ids.str.split("|").str[0]
    m = m.merge(peer_rates(repo), on=["zone_id", "config_id"], how="left")

    ref_rate = float(m.theo_per_available_hour.median())
    ref_hours = float(m.available_hours.median())
    m["reference_win_usd"] = ref_rate * ref_hours
    m["gap_vs_reference_usd"] = m.house_win_usd - m.reference_win_usd
    m["gap_luck_usd"] = m.luck_residual_usd
    m["gap_exposure_usd"] = (m.available_hours - ref_hours) * ref_rate
    m["gap_location_usd"] = (m.zone_theo_per_available_hour - ref_rate) * m.available_hours
    m["gap_game_config_usd"] = (
        m.peer_theo_per_available_hour - m.zone_theo_per_available_hour) * m.available_hours
    m["gap_machine_residual_usd"] = (
        m.theo_per_available_hour - m.peer_theo_per_available_hour) * m.available_hours
    m["machine_vs_zone_index"] = m.theo_per_available_hour / m.zone_theo_per_available_hour
    m["machine_vs_peer_index"] = m.theo_per_available_hour / m.peer_theo_per_available_hour

    m["rank_raw"] = m.house_win_usd.rank(method="first").astype(int)
    m["rank_exposure_adjusted"] = m.win_per_available_hour.rank(method="first").astype(int)
    m["rank_luck_aware"] = m.theo_per_available_hour.rank(method="first").astype(int)
    m["rank_within_zone"] = m.machine_vs_zone_index.rank(method="first").astype(int)
    m["rank_vs_peers"] = m.machine_vs_peer_index.rank(method="first").astype(int)

    boot = bootstrap_bottom_probability(repo, sorted(m.machine_id.tolist()))
    m = m.merge(boot, on="machine_id", how="left")
    m["explanation"] = m.apply(lambda r: classify(r, ref_rate), axis=1)

    rank_cols = ["rank_raw", "rank_exposure_adjusted", "rank_luck_aware", "rank_vs_peers"]
    in_any = m[(m[rank_cols] <= BOTTOM_N).any(axis=1)].copy()
    for c in rank_cols:
        in_any[f"in_bottom_{c.removeprefix('rank_')}"] = in_any[c] <= BOTTOM_N
    in_any = in_any.sort_values("rank_raw")
    return ComparisonResult(m, z, ref_rate, ref_hours, in_any)


def bootstrap_bottom_probability(
    repo: AnalyticsRepository, machine_ids: list[str], draws: int = BOOTSTRAP_DRAWS
) -> pd.DataFrame:
    """Day-resampling bootstrap of theo per available hour.

    Returns a 90% interval per machine and the probability it ranks in the luck-aware
    bottom N. Captures day-to-day demand variation, not structural uncertainty.
    """
    d = repo.query_df("""
        SELECT machine_id, gaming_date, theo_cents::DOUBLE / 100 theo,
               available_seconds / 3600.0 ah
        FROM machine_day WHERE active""")
    theo = d.pivot(index="machine_id", columns="gaming_date", values="theo").reindex(machine_ids)
    ah = d.pivot(index="machine_id", columns="gaming_date", values="ah").reindex(machine_ids)
    t, a = theo.to_numpy(), ah.to_numpy()
    rng = np.random.default_rng(SEED)
    n_m = len(machine_ids)
    rates = np.empty((draws, n_m))
    for i in range(n_m):
        valid = np.flatnonzero(~np.isnan(t[i]))
        idx = rng.choice(valid, size=(draws, valid.size), replace=True)
        rates[:, i] = t[i, idx].sum(axis=1) / np.maximum(a[i, idx].sum(axis=1), 1e-9)
    ranks = rates.argsort(axis=1).argsort(axis=1) + 1
    return pd.DataFrame({
        "machine_id": machine_ids,
        "theo_per_ah_p05": np.percentile(rates, 5, axis=0),
        "theo_per_ah_p95": np.percentile(rates, 95, axis=0),
        "p_bottom_luck_aware": (ranks <= BOTTOM_N).mean(axis=0),
    })


def classify(r: pd.Series, ref_rate: float) -> str:
    """Leading explanation for a machine's position. Tags, not verdicts."""
    tags = []
    if r.hit_p_bonferroni < 0.001:
        tags.append("payout_anomaly")
    if r.active_days < 150 or r.availability_rate < 0.97:
        tags.append("limited_exposure")
    if r.luck_p_bonferroni < 0.05:
        tags.append("significant_luck_shortfall" if r.luck_z < 0 else "significant_luck_gain")
    elif r.luck_z < -1.5:
        tags.append("unlucky_within_chance")
    if r.zone_theo_per_available_hour < 0.85 * ref_rate:
        tags.append("low_demand_location")
    if r.peer_theo_per_available_hour < 0.8 * r.zone_theo_per_available_hour:
        tags.append("low_theo_game_config")
    if r.peer_machines >= 2 and r.machine_vs_peer_index < 0.8:
        tags.append("weak_vs_same_config_peers")
    return ",".join(tags) or "no_distinct_signal"


def persistence_test(repo: AnalyticsRepository) -> dict[str, object]:
    """Competing-explanation test: does a ranking predict the next quarter?

    Rank machines on Jan-Mar by (a) raw house win, (b) win per available hour and
    (c) theo per available hour. If raw bottom-10 status reflects intrinsic weakness it
    should persist into Apr-Jun; if it reflects luck it should regress toward the middle.
    Outcome measured as Apr-Jun house win per available hour percentile.
    """
    h1 = machine_table(repo, "m.gaming_date < DATE '2025-04-01'")
    h2 = machine_table(repo, "m.gaming_date >= DATE '2025-04-01'")
    h1 = h1[h1.available_hours >= 500]  # comparable exposure in both halves
    h2 = h2[h2.available_hours >= 500]
    common = h1.merge(h2[["machine_id", "win_per_available_hour", "theo_per_available_hour"]],
                      on="machine_id", suffixes=("_h1", "_h2"))
    common["h2_win_pctile"] = common.win_per_available_hour_h2.rank(pct=True)
    common["h2_theo_pctile"] = common.theo_per_available_hour_h2.rank(pct=True)
    rankings = {
        "raw_house_win": "house_win_usd",
        "win_per_available_hour": "win_per_available_hour_h1",
        "theo_per_available_hour": "theo_per_available_hour_h1",
    }
    rows = {}
    rng = np.random.default_rng(SEED)
    for label, col in rankings.items():
        bottom = common.nsmallest(BOTTOM_N, col)
        null = [common.sample(BOTTOM_N, random_state=int(rng.integers(1_000_000_000)))
                .h2_win_pctile.mean() for _ in range(2000)]
        rows[label] = {
            "h1_bottom10": bottom.machine_id.tolist(),
            "h2_mean_win_percentile": round(float(bottom.h2_win_pctile.mean()), 3),
            "h2_mean_theo_percentile": round(float(bottom.h2_theo_pctile.mean()), 3),
            "h2_still_bottom_quintile": int((bottom.h2_win_pctile <= 0.2).sum()),
            "p_value_vs_random_10": round(float(np.mean(
                np.array(null) <= bottom.h2_win_pctile.mean())), 4),
        }
    spearman_win = common[["win_per_available_hour_h1", "win_per_available_hour_h2"]].corr(
        "spearman").iloc[0, 1]
    spearman_theo = common[["theo_per_available_hour_h1", "theo_per_available_hour_h2"]].corr(
        "spearman").iloc[0, 1]
    return {
        "machines_compared": len(common),
        "split": "rank on 2025-01-01..2025-03-31, evaluate on 2025-04-01..2025-06-30",
        "rankings": rows,
        "spearman_h1_h2_win_per_ah": round(float(spearman_win), 3),
        "spearman_h1_h2_theo_per_ah": round(float(spearman_theo), 3),
    }
