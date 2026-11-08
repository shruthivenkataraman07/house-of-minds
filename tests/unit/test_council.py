"""Step 4 council: negative/edge cases and gossip comparison on the official data."""

import json
from pathlib import Path

import pytest

from config.settings import get_settings

DATA = Path(get_settings().challenge_data_dir)
LEDGER = Path("data/processed/evidence_ledger.jsonl")
pytestmark = pytest.mark.skipif(not (DATA / "manifest.json").exists() or not LEDGER.exists(),
                                reason="official dataset / Step 1 outputs not present")


@pytest.fixture(scope="module")
def ctx():
    from optimization.action_catalog import ActionCatalog
    from optimization.investment_model import build_model
    from pipelines.ingestion.loader import open_local_repository
    repo = open_local_repository()
    model = build_model(repo, ActionCatalog.load(repo))
    ids = {json.loads(x)["evidence_id"] for x in LEDGER.read_text().splitlines()}
    return repo, model, ids


def test_all_negative_cases_pass(ctx):
    from council.selftest import run_negative_tests
    res = run_negative_tests(*ctx)
    assert len(res) == 21
    assert [r["case"] for r in res if r["status"] != "PASS"] == []


def test_gossip_comparison_is_fair_and_honest(ctx):
    from council.council import run_council
    a, b = run_council(*ctx, gossip=False), run_council(*ctx, gossip=True)
    assert [c.statement for c in a.initial_claims] == [c.statement for c in b.initial_claims]
    assert a.metrics["messages_delivered"] == 0 and b.metrics["messages_delivered"] > 0
    # gossip-derived follow-ups do not inflate independent objections
    assert (b.metrics["independent_decision_relevant_objections"]
            <= b.metrics["verified_decision_relevant_objections"])
    assert b.metrics["retractions"] >= 1 and b.metrics["messages_flagged_retracted_origin"] >= 1


def test_promotion_challenge_flows_to_optimizer(ctx):
    from council.council import run_council
    b = run_council(*ctx, gossip=True)
    stat = [i for i in b.impacts if i["agent_id"] == "AG1_STATISTICIAN"
            and i["mode"] == "evidence_supported"]
    assert stat and stat[0]["portfolio_after"] == "HOLD"
    assert stat[0]["admission_class"] == "VERIFIED_SCENARIO"
    assert stat[0]["constraint_check"] == "OK"
