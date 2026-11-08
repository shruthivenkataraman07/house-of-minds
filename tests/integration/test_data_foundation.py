"""Integration tests against the official dataset (skipped when it is not downloaded)."""

from pathlib import Path

import pytest

from config.settings import get_settings

DATA = Path(get_settings().challenge_data_dir)
pytestmark = pytest.mark.skipif(not (DATA / "manifest.json").exists(),
                                reason="official dataset not downloaded (scripts/fetch_data.sh)")


@pytest.fixture(scope="module")
def repo():
    from pipelines.ingestion.loader import open_local_repository
    return open_local_repository()


@pytest.fixture(scope="module")
def comparison(repo):
    from analytics.machine_performance import compare_machines
    return compare_machines(repo)


def test_manifest_matches_official_hashes():
    from pipelines.ingestion.manifest import build_manifest
    m = build_manifest(DATA)
    assert m["dataset_version"] == "0.9.0-draft"
    assert not m["missing_required"]
    assert all(t["status"] == "verified" for t in m["tables"] if t["status"] != "missing")


@pytest.mark.parametrize("table,rows", [
    ("prepared_daily_view", 56110), ("property_day", 181), ("player_period", 148893),
    ("machine_day", 56110), ("placements", 314), ("operations", 1226),
    ("action_catalog", 13), ("cost_rules", 9), ("calendar_day", 181)])
def test_documented_row_counts(repo, table, rows):
    assert repo.scalar(f"SELECT count(*) FROM {table}") == rows


def test_profile_keys_and_integrity(repo):
    from pipelines.ingestion.catalog import TABLES_BY_NAME
    from pipelines.validation.profiling import profile_table, referential_integrity
    p = profile_table(repo, TABLES_BY_NAME["machine_day"])
    assert p["duplicate_key_groups"] == 0
    assert not [f for f in p["findings"] if f["class"] == "confirmed_error"]
    assert all(r["orphans"] == 0 for r in referential_integrity(repo))


def test_all_reconciliation_checks_pass(repo):
    from pipelines.validation.reconciliation import run_all
    results = run_all(repo)
    assert len(results) == 14
    assert [r.test_id for r in results if r.status != "pass"] == []


def test_carded_is_subset_of_all_play(repo):
    share = repo.scalar("SELECT sum(carded_coin_in_cents)::DOUBLE / sum(coin_in_cents) "
                        "FROM machine_day")
    assert 0 < share < 1


def test_comp_cost_counted_once(repo):
    comp = repo.scalar("SELECT sum(comp_cost_usd) FROM property_day")
    ledger = repo.scalar("SELECT sum(economic_cost_cents) / 100.0 FROM loyalty_ledger "
                         "WHERE event_type = 'redeem'")
    assert float(comp) == pytest.approx(float(ledger), abs=0.01)


def test_decomposition_is_exact(comparison):
    m = comparison.machines
    parts = m[["gap_luck_usd", "gap_exposure_usd", "gap_location_usd", "gap_game_config_usd",
               "gap_machine_residual_usd"]].sum(axis=1)
    assert (parts - m.gap_vs_reference_usd).abs().max() < 1e-6
    assert len(m) == 310 and m.machine_id.is_unique


def test_off_floor_days_excluded(comparison):
    assert comparison.machines.active_days.sum() == 56110 - 1018


def test_rankings_and_bootstrap(comparison):
    m = comparison.machines
    for c in ["rank_raw", "rank_exposure_adjusted", "rank_luck_aware", "rank_vs_peers"]:
        assert sorted(m[c]) == list(range(1, 311))
    assert m.p_bottom_luck_aware.between(0, 1).all()
    assert (m.theo_per_ah_p05 <= m.theo_per_available_hour + 1e-9).all()


def test_contracts_validate(repo, comparison):
    from analytics import contracts as C
    from optimization.action_catalog import ActionCatalog
    assert len(C.machine_performance(comparison)) == 310
    assert len(C.casino_demand(repo)) == 181
    assert len(C.intervention_planning(ActionCatalog.load(repo))) == 13
    for fn in C.BUILDERS.values():
        assert len(fn(repo)) > 0


def test_official_catalog_pricing(repo):
    from optimization.action_catalog import ActionCatalog, SelectedAction, price_selection
    cat = ActionCatalog.load(repo)
    assert price_selection(cat, [SelectedAction(action_type_id="A-REPLACE-LEASE",
                                                quantity=1)]).total_usd == 3380.0
    assert cat.actions["A-TECH-SHIFT"].unit_cost_cents == 1152000


def test_temporal_split(repo):
    from models.temporal_split import ALLOWED_FEATURES, assert_no_leakage, build_daily_frame
    df = build_daily_frame(repo)
    assert df.split.value_counts().to_dict() == {
        "train_inner": 90, "validation_inner": 30, "holdout": 61}
    assert_no_leakage(df, ALLOWED_FEATURES)
