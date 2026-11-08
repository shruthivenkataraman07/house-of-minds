"""Step 3 known-answer tests: optimiser, constraints, reversals, scenarios, invalidation."""

import copy

import pytest

from optimization.action_catalog import ActionCatalog, CatalogAction
from optimization.decision_analysis import invalidation_test, scan_reversals
from optimization.investment_model import (
    ASSUMPTION_REQUIRED,
    EVIDENCE_ESTIMATE,
    Assumption,
    Candidate,
    InvestmentModel,
    economics,
    effective_days,
    promo_weekends,
)
from optimization.portfolio import MODE_CONDITIONAL, MODE_EVIDENCE, evaluate, optimise, verify
from tests.unit.test_action_catalog import ROWS


def catalog() -> ActionCatalog:
    return ActionCatalog(actions={r[0]: CatalogAction(
        action_type_id=r[0], name=r[0], unit=r[1], unit_cost_cents=r[2],
        recurring_cost_cents_per_day=r[3], lead_days=r[4], downtime_minutes=r[5],
        quantity_limit=r[6], incompatibility_group=r[7]) for r in ROWS})


def A(key: str, v: float, lo: float, hi: float, status: str = ASSUMPTION_REQUIRED) -> Assumption:
    return Assumption(key, key, v, lo, hi, "u", status, "synthetic", [], "synthetic")


def synthetic(promo_excess: float = 10_000.0) -> InvestmentModel:
    facts = {"floor_contribution_factor": 1.0, "m1158_factor": 1.0, "m1158_theo_per_ah": 0.0,
             "replace_target_rate": 0.0, "replace_ceiling_rate": 20.0,
             "move_gap_M-X_Z-PIT": 10.0, "move_gap_M-Y_Z-PIT": 9.0}
    assumptions = {a.assumption_id: a for a in [
        A("A01_inspect_fix_probability", 1.0, 0, 1),
        A("A02_m1158_loss_per_day", 100.0, 50, 150, EVIDENCE_ESTIMATE),
        A("A08_promo_excess_theo_per_day", promo_excess, 0, 20_000, EVIDENCE_ESTIMATE),
        A("A09_move_location_transfer", 1.0, 0, 1),
        A("A10_replacement_gap_capture", 1.0, 0, 1)]}
    cands = [
        Candidate("INV-PROMO", "A-PROMO", "w", 2, True, "", ["A08_promo_excess_theo_per_day"],
                  "", EVIDENCE_ESTIMATE, "", []),
        Candidate("INV-INSPECT-M1158", "A-INSPECT", "M-1158", 1, True, "",
                  ["A01_inspect_fix_probability", "A02_m1158_loss_per_day"], "",
                  ASSUMPTION_REQUIRED, "", []),
    ]
    return InvestmentModel(facts, assumptions, cands, catalog(), {"Z-PIT": 2})


def with_moves_and_replace(m: InvestmentModel) -> InvestmentModel:
    m = copy.deepcopy(m)
    for mid in ["M-X", "M-Y"]:
        m.candidates.append(Candidate(
            f"INV-MOVE-{mid}-Z-PIT", "A-MOVE-MACHINE", f"{mid}->Z-PIT", 1, True, "",
            ["A09_move_location_transfer"], "", ASSUMPTION_REQUIRED, "", [], machines=[mid],
            capacity_group="Z-PIT"))
    m.candidates.append(Candidate(
        "INV-REPLACE-LEASE-M-X", "A-REPLACE-LEASE", "M-X", 1, True, "",
        ["A10_replacement_gap_capture"], "", ASSUMPTION_REQUIRED, "", [], machines=["M-X"]))
    return m


def test_timing_rules():
    assert effective_days(14) == 16 and effective_days(21) == 9 and effective_days(30) == 0
    assert promo_weekends(14) == 2  # Jul 18-20, Jul 25-27
    assert promo_weekends(14, delay=7) == 1
    assert promo_weekends(30) == 0


def test_known_optimum_and_verification():
    m = synthetic()
    # promo: 10,000 x 3 days x 1.0 - 15,000 = +15,000 per weekend, 2 weekends
    # inspect: 1.0 x 100 x (29 - 1) days - 1,200 = +1,600
    p = optimise(m, MODE_CONDITIONAL)
    assert p.allocation == {"INV-PROMO": 2, "INV-INSPECT-M1158": 1}
    assert p.net_benefit == pytest.approx(31_600)
    assert p.total_cost == pytest.approx(31_200)
    assert verify(m, p) == []


def test_evidence_mode_excludes_assumption_based():
    p = optimise(synthetic(), MODE_EVIDENCE)
    assert p.allocation == {"INV-PROMO": 2}
    assert "INV-INSPECT-M1158" in p.excluded


def test_negative_net_not_forced():
    p = optimise(synthetic(promo_excess=1_000), MODE_CONDITIONAL)  # promo net -12,000
    assert "INV-PROMO" not in p.allocation and p.net_benefit > 0


def test_budget_is_hard():
    p = optimise(synthetic(), MODE_CONDITIONAL, budget_cents=1_600_000)  # $16,000
    assert p.total_cost <= 16_000
    assert p.allocation == {"INV-PROMO": 1}


def test_max_three_types_and_same_machine_conflict():
    m = with_moves_and_replace(synthetic())
    p = optimise(m, MODE_CONDITIONAL)
    types = {next(c.action_type for c in m.candidates if c.candidate_id == k)
             for k in p.allocation}
    assert len(types) <= 3
    assert not ("INV-MOVE-M-X-Z-PIT" in p.allocation and "INV-REPLACE-LEASE-M-X" in p.allocation)
    assert verify(m, p) == []


def test_slot_capacity():
    m = with_moves_and_replace(synthetic())
    m.capacity["Z-PIT"] = 1
    p = optimise(m, MODE_CONDITIONAL)
    assert sum(q for k, q in p.allocation.items() if k.startswith("INV-MOVE")) <= 1


def test_deterministic_reruns():
    m = with_moves_and_replace(synthetic())
    a, b = optimise(m), optimise(m)
    assert a.allocation == b.allocation and a.portfolio_id == b.portfolio_id
    assert m.fingerprint() == copy.deepcopy(m).fingerprint()


def test_known_reversal_threshold():
    # Choose A (value 60) or B (value 100 v); only one fits -> reversal exactly at v = 0.6
    def solve(v):
        return ("B" if 100 * v > 60 else "A"), None
    revs = scan_reversals(0.0, 1.0, solve)
    assert len(revs) == 1
    assert revs[0]["interval_low"] <= 0.6 <= revs[0]["interval_high"]
    assert revs[0]["interval_high"] - revs[0]["interval_low"] < 1e-3


def test_non_monotone_reversals_detected():
    revs = scan_reversals(0.0, 1.0, lambda v: ("B" if 0.32 < v < 0.71 else "A", None))
    assert len(revs) == 2
    assert revs[0]["interval_low"] <= 0.32 <= revs[0]["interval_high"]
    assert revs[1]["interval_low"] <= 0.71 <= revs[1]["interval_high"]


def test_real_optimizer_reversal_matches_algebra():
    # promo net per weekend = 3 x excess - 15,000 -> enters exactly at excess = 5,000
    m = synthetic()

    def solve(v):
        p = optimise(m.with_assumption("A08_promo_excess_theo_per_day", v), MODE_EVIDENCE)
        return p.signature, p
    revs = scan_reversals(0.0, 20_000.0, solve)
    assert len(revs) == 1 and revs[0]["interval_low"] <= 5_000 <= revs[0]["interval_high"]
    assert revs[0]["from_signature"] == "HOLD"


def test_scenario_propagation_isolated():
    m = synthetic()
    s = m.with_assumption("A01_inspect_fix_probability", 0.0)
    by = {c.candidate_id: c for c in m.candidates}
    assert economics(s, by["INV-INSPECT-M1158"]).net_per_unit < economics(
        m, by["INV-INSPECT-M1158"]).net_per_unit
    assert economics(s, by["INV-PROMO"]).net_per_unit == economics(m, by["INV-PROMO"]).net_per_unit


def test_invalidation_blocks_dependent_decision():
    res = invalidation_test(synthetic(), "A08_promo_excess_theo_per_day", MODE_EVIDENCE)
    assert res["status"] == "PASS" and res["decision_changed"]
    assert res["after"] == "HOLD" and res["dependents_marked_blocked"]


def test_baseline_reevaluation_and_nonnegative_regret():
    m = synthetic()
    base = optimise(m)
    worse = m.with_assumption("A08_promo_excess_theo_per_day", 1_000)
    opt = optimise(worse)
    v_opt, _, _ = evaluate(worse, opt.allocation)
    v_base, _, feasible = evaluate(worse, base.allocation)
    assert feasible and v_opt - v_base >= -1e-6 and v_opt - v_base > 0


def test_move_downtime_uses_the_moved_machines_own_rate():
    # Each move is valued at its own machine's $/h while offline, not one shared rate.
    m = with_moves_and_replace(synthetic())
    m.facts.update(
        {"replace_target_rate": 99.0, "move_own_rate_M-X": 6.0, "move_own_rate_M-Y": 12.0}
    )
    by = {c.candidate_id: c for c in m.candidates}
    dx = economics(m, by["INV-MOVE-M-X-Z-PIT"]).downtime_cost
    dy = economics(m, by["INV-MOVE-M-Y-Z-PIT"]).downtime_cost
    minutes = m.catalog.actions["A-MOVE-MACHINE"].downtime_minutes
    assert dx == pytest.approx(minutes / 60 * 6.0)
    assert dy == pytest.approx(minutes / 60 * 12.0)
