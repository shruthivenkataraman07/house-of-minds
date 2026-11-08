import math

import numpy as np
import pytest

from analytics.metrics import (
    METRICS,
    METRICS_BY_ID,
    bonferroni,
    hit_rate_z,
    luck_z,
    machine_metrics_sql,
    ratio_of_sums,
    two_sided_p_from_z,
)

REQUIRED = ["coin_in", "payout", "house_win", "theo", "observed_hold", "theo_hold",
            "luck_residual", "scheduled_hours", "available_hours", "availability_rate",
            "win_per_available_hour", "downtime_hours", "carded_coin_in", "carded_payout",
            "player_net", "comp_cost", "supplied_machine_costs"]


def test_registry_covers_required_metrics_once():
    ids = [m.id for m in METRICS]
    assert len(ids) == len(set(ids))
    assert set(REQUIRED) <= set(METRICS_BY_ID)
    for m in METRICS:
        assert m.formula and m.source and m.unit and m.grain


def test_ratio_of_sums_differs_from_mean_of_ratios():
    win, coin = np.array([10.0, 1.0]), np.array([100.0, 1000.0])
    assert ratio_of_sums(win, coin) == pytest.approx(11 / 1100)
    assert np.mean(win / coin) != pytest.approx(ratio_of_sums(win, coin))
    assert ratio_of_sums(win, np.zeros(2)) is None


def test_luck_and_hit_z():
    assert luck_z(90, 100, 5) == pytest.approx(-2)
    assert luck_z(1, 1, 0) is None
    assert hit_rate_z(500, 1000, 0.5) == 0
    assert hit_rate_z(600, 1000, 0.5) == pytest.approx(100 / math.sqrt(250))
    assert hit_rate_z(1, 0, 0.5) is None


def test_pvalues():
    assert two_sided_p_from_z(1.96) == pytest.approx(0.05, abs=1e-3)
    assert bonferroni(0.01, 310) == 1.0
    assert bonferroni(1e-6, 310) == pytest.approx(3.1e-4)


def test_machine_sql_always_excludes_off_floor():
    sql = machine_metrics_sql(["m.machine_id"], "m.gaming_date < DATE '2025-04-01'")
    assert "m.active AND" in sql and "SUM(m.house_win_cents)" in sql
