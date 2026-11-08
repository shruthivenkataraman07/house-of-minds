"""Independent reconciliation of every decision passport's net benefit.

The optimizer computes, per unit, net = contribution + avoided - downtime - cost
(optimization.investment_model.economics). Passports export only contribution and cost; the
downtime term comes from the sidecar `investment_economics` (Step 3 investment_candidates).
These tests recompute each passport's net from those components, read straight from the
snapshot files, and check the API serves the same values.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app

DATA = Path(__file__).resolve().parents[2] / "web" / "public" / "data"
PASSPORTS = json.loads((DATA / "current" / "dash_decision_passports.json").read_text())
ECON = {
    r["investment_id"]: r
    for r in json.loads((DATA / "sidecar" / "investment_economics.json").read_text())
}


@pytest.mark.parametrize("p", PASSPORTS, ids=[p["passport_id"] for p in PASSPORTS])
def test_passport_net_reconciles_with_optimizer_components(p: dict) -> None:
    e = ECON[p["investment_id"]]
    q = p["quantity"]
    recomputed = q * (
        e["contribution_gain"] + e["avoided_costs"] - e["downtime_cost"] - e["unit_cost"]
    )
    assert recomputed == pytest.approx(p["modeled_net_contribution"], abs=0.01)
    # the exported contribution and cost are the same terms, scaled by quantity
    assert q * e["contribution_gain"] == pytest.approx(p["modeled_incremental_effect"], abs=0.01)
    assert q * e["unit_cost"] == pytest.approx(p["total_cost"], abs=0.01)
    # and the per-unit net is the optimizer's own base value
    assert e["benefit_base"] * q == pytest.approx(p["modeled_net_contribution"], abs=0.01)


def test_three_gaps_are_exactly_the_downtime_term() -> None:
    gaps = {}
    for p in PASSPORTS:
        g = p["modeled_incremental_effect"] - p["total_cost"] - p["modeled_net_contribution"]
        gaps[p["investment_id"]] = (g, p["quantity"] * ECON[p["investment_id"]]["downtime_cost"])
    for inv in ("INV-INSPECT-M1158", "INV-MOVE-M-1154-Z-PIT", "INV-MOVE-M-1184-Z-PIT"):
        gap, down = gaps[inv]
        assert gap > 1
        assert gap == pytest.approx(down, abs=1e-6)


def test_api_serves_the_downtime_term() -> None:
    client = TestClient(app)
    for p in PASSPORTS:
        v = client.get(f"/api/v1/evidence/{p['passport_id']}").json()["data"]["values"]
        e = ECON[p["investment_id"]]
        assert v["downtime_cost"] == pytest.approx(p["quantity"] * e["downtime_cost"], abs=1e-9)
        net = (
            v["modeled_incremental_effect"]
            + v["avoided_costs"]
            - v["downtime_cost"]
            - v["quantity"] * v["unit_cost"]
        )
        assert net == pytest.approx(v["modeled_net_contribution"], abs=0.01)
