"""Machine statistical diagnostics for the dashboard (adds to analytics.machine_performance).

New here (existing luck z, Bonferroni hit-rate z, decomposition and day bootstrap are reused):
* Payout Monte Carlo of the RAW earnings ranking. Each machine's house win is redrawn as
  theo + sd * N(0, 1), where sd = sqrt(sum(bet^2) * payout-multiplier variance) from game math
  (independent spins; normal approximation by the central limit theorem over >=10^4 spins).
  Exposure, game and bets are held fixed, so only payout luck varies.
* Leave-one-out peer index: machine theo/hour vs the same zone + game cell excluding itself;
  falls back to same game floor-wide when the cell has no other machine.
* Exact binomial p-value for paying-spin frequency (scipy), Bonferroni across machines.
* Decomposition identity check: luck + exposure + location + game + residual must equal the
  observed gap to the reference machine (a sequential accounting identity, not causal).
* Walkway-closure event series: Back Forty vs rest of floor, fixed machine set.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from analytics.machine_performance import BOTTOM_N, SEED, compare_machines
from backend.repositories.base import AnalyticsRepository

SIMS = 2000


def machine_diagnostics(repo: AnalyticsRepository) -> tuple[pd.DataFrame, dict[str, Any]]:
    cmp = compare_machines(repo)
    m = cmp.machines.sort_values("machine_id").reset_index(drop=True)

    # --- payout Monte Carlo of the raw ranking (fair ranking uses theo, so luck cannot move it)
    rng = np.random.default_rng(SEED)
    theo = m.theo_usd.to_numpy()
    sd = m.luck_residual_sd_usd.to_numpy()
    sims = theo[None, :] + sd[None, :] * rng.standard_normal((SIMS, len(m)))
    ranks = sims.argsort(axis=1).argsort(axis=1) + 1
    in_b10 = ranks <= BOTTOM_N
    m["p_raw_bottom10_sim"] = in_b10.mean(axis=0)
    m["raw_rank_p05_sim"] = np.percentile(ranks, 5, axis=0)
    m["raw_rank_p95_sim"] = np.percentile(ranks, 95, axis=0)
    mgr = m.rank_raw.to_numpy() <= BOTTOM_N
    overlap = (in_b10 & mgr[None, :]).sum(axis=1)

    # --- leave-one-out peer reference (same zone + game, excluding the machine)
    m["theo_hours"] = m.theo_usd
    cell = (
        m.groupby(["zone_id", "config_id"])
        .agg(
            cell_theo=("theo_usd", "sum"),
            cell_ah=("available_hours", "sum"),
            cell_n=("machine_id", "count"),
        )
        .reset_index()
    )
    game = (
        m.groupby("config_id")
        .agg(
            game_theo=("theo_usd", "sum"),
            game_ah=("available_hours", "sum"),
            game_n=("machine_id", "count"),
        )
        .reset_index()
    )
    m = m.merge(cell, on=["zone_id", "config_id"], how="left").merge(
        game, on="config_id", how="left"
    )
    loo_cell = (m.cell_theo - m.theo_usd) / (m.cell_ah - m.available_hours)
    loo_game = (m.game_theo - m.theo_usd) / (m.game_ah - m.available_hours)
    use_cell = m.cell_n >= 2
    m["loo_peer_rate"] = np.where(use_cell, loo_cell, loo_game)
    m["loo_peer_basis"] = np.where(
        use_cell, "same zone and game", "same game, floor-wide (sparse cell)"
    )
    m["loo_peer_n"] = np.where(use_cell, m.cell_n - 1, m.game_n - 1)
    m["loo_peer_index"] = m.theo_per_available_hour / m.loo_peer_rate

    # --- exact binomial test of paying-spin frequency
    p_exact = [
        float(stats.binomtest(int(h), int(n), float(p)).pvalue) if n and p == p else np.nan
        for h, n, p in zip(m.hits.fillna(0), m.spins_cfg.fillna(0), m.p, strict=True)
    ]
    m["hit_p_exact"] = p_exact
    m["hit_p_exact_bonferroni"] = np.minimum(np.array(p_exact) * len(m), 1.0)

    # --- decomposition identity
    parts = [
        "gap_luck_usd",
        "gap_exposure_usd",
        "gap_location_usd",
        "gap_game_config_usd",
        "gap_machine_residual_usd",
    ]
    m["decomposition_sum_usd"] = m[parts].sum(axis=1)
    m["decomposition_error_usd"] = m.decomposition_sum_usd - m.gap_vs_reference_usd

    cols = [
        "machine_id",
        "house_win_usd",
        "theo_usd",
        "luck_residual_usd",
        "luck_residual_sd_usd",
        "luck_z",
        "luck_p_bonferroni",
        "hits",
        "spins_cfg",
        "p",
        "observed_hit_rate",
        "hit_rate_z_cfg",
        "hit_p_exact",
        "hit_p_exact_bonferroni",
        "rank_raw",
        "p_raw_bottom10_sim",
        "raw_rank_p05_sim",
        "raw_rank_p95_sim",
        "p_bottom_luck_aware",
        "machine_vs_peer_index",
        "loo_peer_index",
        "loo_peer_rate",
        "loo_peer_basis",
        "loo_peer_n",
        "reference_win_usd",
        "gap_vs_reference_usd",
        *parts,
        "decomposition_sum_usd",
        "decomposition_error_usd",
    ]
    out = m[cols].rename(
        columns={"spins_cfg": "paid_spins", "hits": "paying_spins", "p": "expected_hit_probability"}
    )
    summary = {
        "simulations": SIMS,
        "seed": SEED,
        "method": "house win redrawn as theo + sd*N(0,1); sd = sqrt(sum(bet^2) x payout-multiplier variance)",
        "assumption": "independent spins; normal approximation (CLT); exposure, bets and game fixed",
        "manager_list_mean_overlap": float(overlap.mean()),
        "manager_list_all10_share": float((overlap == BOTTOM_N).mean()),
        "manager_list_overlap_p05": float(np.percentile(overlap, 5)),
        "fair_ranking_note": "fair ranking uses expected win per available hour, which payout luck does not change",
        "decomposition_max_abs_error_usd": float(np.abs(m.decomposition_error_usd).max()),
        "decomposition_note": "sequential accounting identity: exposure valued at the reference rate, "
        "then location, game and machine at the machine's own hours; order-dependent, not causal",
        "reference_rate_usd_per_hour": cmp.reference_rate,
        "reference_hours": cmp.reference_hours,
    }
    return out, summary


def walkway_event_series(repo: AnalyticsRepository) -> dict[str, Any]:
    """Daily Back Forty vs rest-of-floor expected win per available hour (fixed machine set)."""
    d = repo.query_df("""
        WITH stable AS (SELECT machine_id FROM prepared_daily_view
                        GROUP BY 1 HAVING count(*) FILTER (WHERE active) = 181
                        AND count(DISTINCT zone_id) = 1)
        SELECT p.gaming_date, (p.zone_id = 'Z-B40') treated,
               sum(m.theo_cents)::DOUBLE / 100 theo, sum(m.available_seconds) / 3600.0 ah
        FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
        WHERE m.active AND m.machine_id IN (SELECT machine_id FROM stable)
        GROUP BY 1, 2 ORDER BY 1""")
    piv = d.pivot(index="gaming_date", columns="treated", values=["theo", "ah"])
    rows = [
        {
            "gaming_date": str(k)[:10],
            "back_forty": float(piv["theo"][True][k] / piv["ah"][True][k]),
            "rest_of_floor": float(piv["theo"][False][k] / piv["ah"][False][k]),
        }
        for k in piv.index
    ]
    return {
        "event": "Entrance-Back Forty walkway closed for renovation",
        "closed_from": "2025-03-03",
        "closed_to": "2025-04-06",
        "unit": "expected win per available machine-hour, USD",
        "machines": "fixed set active all 181 days in one zone",
        "rows": rows,
    }
