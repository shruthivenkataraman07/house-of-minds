"""Decision-Reversal Engine, scenario re-optimisation, regret and assumption invalidation.

Every reported reversal comes from actually re-running the optimiser on both sides of the
boundary. Boundaries are reported as bounded intervals (bisection), never as exact
thresholds. Scenarios are sensitivity analyses, not predictions or causal effects.
"""

from __future__ import annotations

import copy
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from optimization.investment_model import EVIDENCE_ESTIMATE, InvestmentModel
from optimization.portfolio import (
    MODE_CONDITIONAL,
    MODE_EVIDENCE,
    Portfolio,
    evaluate,
    optimise,
)

GRID_POINTS = 21
BISECT_STEPS = 12


# --------------------------------------------------------------------------- generic engine
def scan_reversals(lo: float, hi: float, solve: Callable[[float], tuple[str, Any]],
                   grid: int = GRID_POINTS, steps: int = BISECT_STEPS) -> list[dict[str, Any]]:
    """Find every change of optimal decision `signature` on [lo, hi].

    `solve(v)` returns (signature, payload). Change points between grid neighbours are
    refined by bisection to an interval [a, b] with signature(a) != signature(b).
    Non-monotone patterns (A -> B -> A) are reported as separate reversals.
    """
    xs = np.linspace(lo, hi, grid)
    sols = [solve(float(x)) for x in xs]
    out = []
    for i in range(len(xs) - 1):
        (s0, p0), (s1, p1) = sols[i], sols[i + 1]
        if s0 == s1:
            continue
        a, b = float(xs[i]), float(xs[i + 1])
        sa, pa, sb, pb = s0, p0, s1, p1
        for _ in range(steps):
            mid = (a + b) / 2
            sm, pm = solve(mid)
            if sm == sa:
                a, pa = mid, pm
            else:
                b, sb, pb = mid, sm, pm
        out.append({"interval_low": a, "interval_high": b, "from_signature": sa,
                    "to_signature": sb, "from_payload": pa, "to_payload": pb,
                    "grid_points": grid, "bisection_steps": steps})
    return out


# --------------------------------------------------------------------------- reversals
@dataclass
class ReversalRecord:
    assumption_id: str
    mode: str
    evidence_ids: str
    baseline_value: float
    tested_low: float
    tested_high: float
    interval_low: float | None
    interval_high: float | None
    original_portfolio: str
    replacement_portfolio: str | None
    original_portfolio_id: str
    replacement_portfolio_id: str | None
    net_change_at_boundary: float | None
    reversal_found: bool
    within_tested_range: bool
    within_empirical_range: bool | None
    risk_class: str
    limitations: str


def decision_reversals(model: InvestmentModel) -> list[ReversalRecord]:
    records = []
    for mode in (MODE_CONDITIONAL, MODE_EVIDENCE):
        base_p = optimise(model, mode)
        for key, a in sorted(model.assumptions.items()):
            if mode == MODE_EVIDENCE and a.status != EVIDENCE_ESTIMATE:
                continue  # assumption-based inputs cannot move the evidence decision

            def solve(v: float, key: str = key, mode: str = mode) -> tuple[str, Portfolio]:
                p = optimise(model.with_assumption(key, v), mode)
                return p.signature, p

            revs = scan_reversals(a.low, a.high, solve)
            if not revs:
                records.append(ReversalRecord(
                    key, mode, ",".join(a.evidence_ids), a.value, a.low, a.high, None, None,
                    base_p.signature, None, base_p.portfolio_id, None, None, False, False,
                    None, "LOW", f"No change of optimal portfolio across the tested range "
                                 f"({GRID_POINTS} grid points)."))
                continue
            span = a.high - a.low or 1.0
            for r in revs:
                b = r["interval_high"]
                at_b = model.with_assumption(key, b)
                new_net, _, _ = evaluate(at_b, r["to_payload"].allocation)
                old_net, _, _ = evaluate(at_b, r["from_payload"].allocation)
                near = min(abs(r["interval_low"] - a.value), abs(b - a.value)) / span
                empirical = a.status == EVIDENCE_ESTIMATE  # range = observed evidence range
                risk = "HIGH" if (empirical or near <= 0.25) else "MEDIUM"
                records.append(ReversalRecord(
                    key, mode, ",".join(a.evidence_ids), a.value, a.low, a.high,
                    r["interval_low"], r["interval_high"], r["from_signature"],
                    r["to_signature"], r["from_payload"].portfolio_id,
                    r["to_payload"].portfolio_id, new_net - old_net, True, True,
                    True if a.status == EVIDENCE_ESTIMATE else None, risk,
                    f"Boundary bounded to [{r['interval_low']:.6g}, {b:.6g}] by bisection; "
                    f"assumption status {a.status}; causal status {a.causal_status}."))
    return records


# --------------------------------------------------------------------------- scenarios
SCENARIOS: list[dict[str, Any]] = [
    {"id": "S01_demand_low", "kind": "exploratory_stress", "demand_multiplier": 0.9,
     "desc": "All play-driven benefits 10% lower"},
    {"id": "S02_demand_high", "kind": "exploratory_stress", "demand_multiplier": 1.1,
     "desc": "All play-driven benefits 10% higher"},
    {"id": "S03_downtime_recovery_low", "kind": "assumption_sensitivity",
     "set": {"A04_preventive_effectiveness": 0.0, "A05_tech_downtime_reduction": 0.0},
     "desc": "Maintenance and technicians recover no downtime"},
    {"id": "S04_b40_partial_recovery", "kind": "assumption_sensitivity", "b40_multiplier": 0.9,
     "desc": "Back Forty demand 10% below its post-reopening level"},
    {"id": "S05a_comp_response_low", "kind": "assumption_sensitivity",
     "set": {"A06_comp_play_response": 0.0}, "desc": "Guests do not react to comp pricing"},
    {"id": "S05b_comp_response_high", "kind": "assumption_sensitivity",
     "set": {"A06_comp_play_response": 0.05}, "desc": "Guests cut play 5% if comps cost more"},
    {"id": "S06_cost_overrun", "kind": "exploratory_stress", "cost_multiplier": 1.2,
     "desc": "Execution costs 20% above catalog"},
    {"id": "S07_delayed_implementation", "kind": "exploratory_stress", "lead_delay_days": 7,
     "desc": "Every action starts 7 days later than its catalog lead time"},
    {"id": "S08_promo_low", "kind": "empirical_bound",
     "set_bound": {"A08_promo_excess_theo_per_day": "low"},
     "desc": "Promotion effect at the weaker of the two observed promotions"},
    {"id": "S09_promo_high", "kind": "empirical_bound",
     "set_bound": {"A08_promo_excess_theo_per_day": "high"},
     "desc": "Promotion effect at the stronger observed promotion"},
    {"id": "S10_inspection_fails", "kind": "assumption_sensitivity",
     "set": {"A01_inspect_fix_probability": 0.0}, "desc": "Inspection does not fix M-1158"},
    {"id": "S11_m1158_loss_low", "kind": "empirical_bound",
     "set_bound": {"A02_m1158_loss_per_day": "low"},
     "desc": "M-1158 loss at the low end of its luck interval"},
    {"id": "S12_moves_no_transfer", "kind": "assumption_sensitivity",
     "set": {"A09_move_location_transfer": 0.0},
     "desc": "Moved machines keep their old demand"},
]


def scenario_model(model: InvestmentModel, s: dict[str, Any]) -> InvestmentModel:
    m = copy.deepcopy(model)
    m.scenario_id = s["id"]
    for k in ("demand_multiplier", "cost_multiplier", "lead_delay_days", "b40_multiplier"):
        if k in s:
            setattr(m, k, s[k])
    for k, v in s.get("set", {}).items():
        m.assumptions[k].value = v
    for k, side in s.get("set_bound", {}).items():
        m.assumptions[k].value = getattr(m.assumptions[k], side)
    return m


def run_scenarios(model: InvestmentModel, baseline: Portfolio,
                  mode: str = MODE_CONDITIONAL) -> list[dict[str, Any]]:
    rows = []
    for s in SCENARIOS:
        sm = scenario_model(model, s)
        opt = optimise(sm, mode)
        opt_net, _, _ = evaluate(sm, opt.allocation)  # same (unrounded) arithmetic both sides
        base_net, base_cost, base_feasible = evaluate(sm, baseline.allocation)
        regret = opt_net - base_net
        rows.append({
            "scenario_id": s["id"], "scenario_kind": s["kind"], "description": s["desc"],
            "mode": mode, "modified_inputs": str({k: v for k, v in s.items()
                                                  if k not in ("id", "kind", "desc")}),
            "optimal_portfolio_id": opt.portfolio_id, "optimal_portfolio": opt.signature,
            "optimal_cost": opt.total_cost, "unspent_budget": 100000 - opt.total_cost,
            "optimal_net_benefit": opt_net,
            "baseline_portfolio_id": baseline.portfolio_id,
            "baseline_net_under_scenario": base_net, "baseline_cost_under_scenario": base_cost,
            "baseline_feasible_under_scenario": base_feasible,
            "regret": regret, "baseline_still_optimal": regret <= 0.05,
            "composition_changed": opt.signature != baseline.signature,
            "difference_vs_baseline_net": opt.net_benefit - baseline.net_benefit,
            "_allocation": opt.allocation,
        })
    return rows


def regret_summary(model: InvestmentModel, baseline: Portfolio,
                   rows: list[dict[str, Any]]) -> dict[str, Any]:
    regrets = [r["regret"] for r in rows]
    worst = max(rows, key=lambda r: r["regret"])
    # Downside-aware alternative: minimax regret over the tested candidate portfolios
    pool = {baseline.signature: baseline.allocation, "HOLD": {}}
    for r in rows:
        pool[r["optimal_portfolio"]] = r["_allocation"]
    best_by_s = {r["scenario_id"]: r["optimal_net_benefit"] for r in rows}
    table = []
    for sig, alloc in sorted(pool.items()):
        regs = []
        for s in SCENARIOS:
            v, _, _ = evaluate(scenario_model(model, s), alloc)
            regs.append(best_by_s[s["id"]] - v)
        base_v, _, _ = evaluate(model, alloc)
        table.append({"portfolio": sig, "max_regret": max(regs), "base_net": base_v})
    alt = min(table, key=lambda t: (round(t["max_regret"], 2), -t["base_net"], t["portfolio"]))
    return {
        "scenarios": len(rows),
        "max_regret": max(regrets), "median_regret": statistics.median(regrets),
        "mean_regret_unweighted": float(np.mean(regrets)),
        "baseline_optimal_count": sum(r["baseline_still_optimal"] for r in rows),
        "baseline_optimal_share": sum(r["baseline_still_optimal"] for r in rows) / len(rows),
        "worst_scenario": worst["scenario_id"], "worst_scenario_optimal": worst[
            "optimal_portfolio"],
        "minimax_regret_portfolio": alt["portfolio"],
        "minimax_regret_value": alt["max_regret"],
        "baseline_max_regret": next(t["max_regret"] for t in table
                                    if t["portfolio"] == baseline.signature),
        "cost_of_conservatism": baseline.net_benefit - alt["base_net"],
        "candidate_portfolios": table,
        "note": "Scenario probabilities are unknown: no expected regret or expected return "
                "is claimed. Robustness here does not make the benefit assumptions true.",
    }


# --------------------------------------------------------------------------- invalidation
def invalidation_test(model: InvestmentModel, assumption_id: str,
                      mode: str = MODE_CONDITIONAL) -> dict[str, Any]:
    """Mark an assumption invalid: dependent candidates must be BLOCKED and re-optimised."""
    before = optimise(model, mode)
    m = copy.deepcopy(model)
    m.assumptions[assumption_id].valid = False
    after = optimise(m, mode)
    dependents = [c.candidate_id for c in m.candidates if assumption_id in c.assumptions]
    still_used = [d for d in dependents if d in after.allocation]
    return {"assumption_id": assumption_id, "mode": mode,
            "dependent_candidates": dependents,
            "before": before.signature, "after": after.signature,
            "decision_changed": before.signature != after.signature,
            "blocked_candidates_still_selected": still_used,
            "dependents_marked_blocked": all(after.excluded.get(d) == "BLOCKED"
                                             for d in dependents),
            "status": "PASS" if not still_used else "FAIL"}
