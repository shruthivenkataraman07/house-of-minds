"""Official challenge alignment: verdict rules and invariants."""

import json
from pathlib import Path

import pandas as pd
import pytest

from config.settings import get_settings

DATA = Path(get_settings().challenge_data_dir)
LEDGER = Path("data/processed/evidence_ledger.jsonl")
real = pytest.mark.skipif(not (DATA / "manifest.json").exists() or not LEDGER.exists(),
                          reason="official dataset not present")


def test_overall_verdict_can_return_every_outcome():
    import importlib.util
    spec = importlib.util.spec_from_file_location("rc", "scripts/run_challenge.py")
    rc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rc)  # type: ignore[union-attr]

    def rows(*vs: str) -> list[dict[str, str]]:
        return [{"verdict": v} for v in vs]
    J, N, INS, R = ("REPLACE_JUSTIFIED_CONDITIONAL", "DO_NOT_REPLACE_NOT_ECONOMIC",
                  "INSUFFICIENT_EVIDENCE", "RETIRED_ALREADY")
    assert rc.overall(rows(J, J, R)) == "REPLACE_ALL"  # retired excluded from eligibility
    assert rc.overall(rows(J, N, N)) == "REPLACE_SOME"
    assert rc.overall(rows(N, N, INS)) == "REPLACE_NONE"
    assert rc.overall(rows(INS, INS, N)) == "INSUFFICIENT_EVIDENCE"


@pytest.fixture(scope="module")
def ctx():
    from analytics.replacement import compare_portfolios, verdicts
    from optimization.action_catalog import ActionCatalog
    from optimization.investment_model import build_model
    from pipelines.ingestion.loader import open_local_repository
    repo = open_local_repository()
    model = build_model(repo, ActionCatalog.load(repo))
    v = verdicts(repo, model)
    return repo, model, v, compare_portfolios(model, v["model_with_replacements"], v["rows"])


@real
def test_verdicts_follow_their_evidence(ctx):
    _, _, v, _ = ctx
    df = pd.DataFrame(v["rows"])
    assert len(df) == 10 and df.machine_id.is_unique
    retired = df.retire_date.notna() & (pd.to_datetime(df.retire_date) <= "2025-06-30")
    assert (df[retired].verdict == "RETIRED_ALREADY").all()
    inspect = ~retired & (df.hit_p_bonferroni < 0.001)
    assert (df[inspect].verdict == "DO_NOT_REPLACE_INSPECT").all()
    uneconomic = df.verdict == "DO_NOT_REPLACE_NOT_ECONOMIC"
    assert (df[uneconomic].lease_net_best_case_usd <= 0).all()
    insufficient = df.verdict == "INSUFFICIENT_EVIDENCE"
    assert (df[insufficient].lease_net_planning_usd <= 0).all()


@real
def test_incremental_not_total_revenue(ctx):
    _, _, v, _ = ctx
    c = v["candidates"]
    # gain is (ceiling - own) x hours: a machine at/above its zone ceiling gains nothing
    assert (c.zone_ceiling_rate > c.own_rate).all()


@real
def test_portfolio_comparison_invariants(ctx):
    _, _, v, comp = ctx
    by = {c["option"]: c for c in comp}
    assert not by["manager_proposal_buy"]["feasible"]
    for c in comp:
        if c["feasible"]:
            assert c["cost_usd"] <= 100000 and c["action_types"] <= 3
            assert c["horizon"] == "2025-07-01..2025-07-30"
    on_floor = [r for r in v["rows"] if r["verdict"] != "RETIRED_ALREADY"]
    assert by["manager_proposal_lease"]["cost_usd"] == pytest.approx(3380 * len(on_floor))
    assert by["no_action"]["expected_net_benefit_usd"] == 0
    # the optimiser, offered replacements, is free to choose them; its choice is recorded
    assert by["house_of_minds_with_replacements_allowed"]["feasible"]


@real
def test_council_review_reproduces_and_agrees(ctx):
    repo, _, v, _ = ctx
    from council.manager_review import run_manager_review
    ids = {json.loads(x)["evidence_id"] for x in LEDGER.read_text().splitlines()}
    rv = run_manager_review(repo, v["model_with_replacements"], ids,
                            list(v["bottom10"].machine_id))
    assert all(x.arithmetic_valid for x in rv["verifications"].values())
    an = {r["machine_id"]: r["verdict"] for r in v["rows"]}
    assert all(r["council_verdict"] == an[r["machine_id"]] for r in rv["resolutions"])
