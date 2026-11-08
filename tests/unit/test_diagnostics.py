"""Independent checks for analytics.diagnostics (raw parquet recomputation where possible)."""

from __future__ import annotations

import math
from pathlib import Path

import duckdb
import pytest

from config.settings import get_settings

RAW = Path(get_settings().challenge_data_dir)
pytestmark = pytest.mark.skipif(not (RAW / "manifest.json").exists(), reason="official dataset not present")


@pytest.fixture(scope="module")
def diag():
    from analytics.diagnostics import machine_diagnostics
    from pipelines.ingestion.loader import open_local_repository

    d, s = machine_diagnostics(open_local_repository())
    return d.set_index("machine_id"), s


def raw(sql: str):
    con = duckdb.connect()
    con.sql(f"CREATE VIEW md AS SELECT * FROM '{RAW}/2_machine_decision/machine_day.parquet'")
    con.sql(f"CREATE VIEW gm AS SELECT * FROM '{RAW}/2_machine_decision/game_math.parquet'")
    return con.sql(sql).fetchall()


def test_wager_payout_identity_and_luck_variance(diag):
    d, _ = diag
    hw, theo, var = raw("""SELECT sum(house_win_cents)/100.0, sum(theo_cents)/100.0,
        sum(sum_bet_squared * payout_multiplier_variance) FROM md JOIN gm USING (config_id)
        WHERE machine_id = 'M-5076' AND active""")[0]
    r = d.loc["M-5076"]
    assert r.house_win_usd == pytest.approx(hw, abs=0.01)
    assert r.theo_usd == pytest.approx(theo, abs=0.01)
    assert r.luck_residual_sd_usd == pytest.approx(math.sqrt(var) / 100, rel=1e-9)
    assert r.luck_z == pytest.approx((hw - theo) / (math.sqrt(var) / 100), rel=1e-9)


def test_exact_binomial_and_multiple_comparisons(diag):
    from scipy import stats

    d, _ = diag
    hits, spins, p = raw("""SELECT sum(payout_positive_spins), sum(paid_spins), any_value(hit_probability)
        FROM md JOIN gm USING (config_id) WHERE machine_id = 'M-1158' AND active""")[0]
    pv = stats.binomtest(int(hits), int(spins), float(p)).pvalue
    assert d.loc["M-1158", "hit_p_exact"] == pytest.approx(pv, abs=1e-300)
    assert d.loc["M-1158", "hit_p_exact_bonferroni"] == pytest.approx(min(pv * len(d), 1.0), abs=1e-300)
    assert d.loc["M-1158", "hit_p_exact_bonferroni"] < 0.001  # anomaly survives correction
    assert d.loc["M-5076", "hit_p_exact_bonferroni"] > 0.05  # no anomaly


def test_decomposition_is_an_exact_identity(diag):
    d, s = diag
    assert (d.decomposition_error_usd.abs() < 1e-6).all()
    assert s["decomposition_max_abs_error_usd"] < 1e-6
    assert "not causal" in s["decomposition_note"]


def test_leave_one_out_excludes_the_machine(diag):
    d, _ = diag
    from pipelines.ingestion.loader import open_local_repository

    repo = open_local_repository()
    zone, cfg = repo.query_df("""SELECT p.zone_id, m.config_id FROM machine_day m JOIN prepared_daily_view p
        USING (machine_id, gaming_date) WHERE m.machine_id = 'M-1120' AND m.active
        GROUP BY 1, 2 ORDER BY count(*) DESC LIMIT 1""").iloc[0].tolist()
    peers = d[(d.index != "M-1120")]
    # independent leave-one-out: same zone + game, other machines only
    cell = repo.query_df(f"""SELECT sum(theo_cents)/100.0 / (sum(available_seconds)/3600.0), count(DISTINCT m.machine_id)
        FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
        WHERE m.active AND p.zone_id = '{zone}' AND m.config_id = '{cfg}' AND m.machine_id <> 'M-1120'""").iloc[0].tolist()
    assert len(peers) == len(d) - 1
    assert d.loc["M-1120", "loo_peer_n"] >= 1
    assert d.loc["M-1120", "loo_peer_rate"] == pytest.approx(cell[0], rel=0.02)


def test_monte_carlo_reproducible_and_bounded(diag):
    from analytics.diagnostics import machine_diagnostics
    from pipelines.ingestion.loader import open_local_repository

    d, s = diag
    d2, s2 = machine_diagnostics(open_local_repository())
    assert (d2.set_index("machine_id").p_raw_bottom10_sim == d.p_raw_bottom10_sim).all()
    assert s2["manager_list_mean_overlap"] == s["manager_list_mean_overlap"]
    assert d.p_raw_bottom10_sim.between(0, 1).all()
    assert d.p_raw_bottom10_sim.sum() == pytest.approx(10.0, abs=1e-9)  # exactly 10 per draw
    assert (d.raw_rank_p05_sim <= d.raw_rank_p95_sim).all()


def test_retired_and_new_machines_use_active_exposure_only(diag):
    d, _ = diag
    for mid in ("M-1118", "M-1120", "M-5076"):
        ah = raw(f"SELECT sum(available_seconds)/3600.0 FROM md WHERE machine_id = '{mid}' AND active")[0][0]
        ah_all = raw(f"SELECT sum(available_seconds)/3600.0 FROM md WHERE machine_id = '{mid}'")[0][0]
        theo = raw(f"SELECT sum(theo_cents)/100.0 FROM md WHERE machine_id = '{mid}' AND active")[0][0]
        assert d.loc[mid, "theo_usd"] == pytest.approx(theo, abs=0.01)
        assert ah <= ah_all + 1e-9  # off-floor rows excluded, never added


def test_api_exposes_diagnostics_consistently():
    from fastapi.testclient import TestClient

    from backend.main import app

    c = TestClient(app)
    st = c.get("/api/v1/machines/stability").json()
    ids = {r["machine_id"] for r in st["data"]["rows"]}
    mgr = {m["machine_id"] for m in c.get("/api/v1/executive").json()["data"]["bottom10"]}
    assert mgr <= ids
    m = c.get("/api/v1/machines/M-1158").json()["data"]["diagnostics"]
    row = next(r for r in st["data"]["rows"] if r["machine_id"] == "M-1158")
    assert m["p_raw_bottom10_sim"] == row["p_raw_bottom10_sim"]
    ev = c.get("/api/v1/operations/events").json()["data"]
    assert len(ev["rows"]) == 181 and ev["closed_from"] == "2025-03-03"
    a = c.post("/api/v1/ask", json={"question": "How stable is this ranking?"}).json()
    assert a["status"] == "OK" and f"{st['data']['summary']['manager_list_mean_overlap']:.1f}" in a["conclusion"]
    w = c.post("/api/v1/ask", json={"question": "What happened during the walkway closure?"}).json()
    assert "-31.2%" in w["conclusion"]
