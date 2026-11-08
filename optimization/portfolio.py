"""Exact $100,000 portfolio optimisation over admissible candidates (SciPy MILP / HiGHS).

Integer quantities, hard budget, quantity limits, <=3 funded action types, comp_policy
incompatibility, same_machine conflicts, shared destination-slot capacity, lead-time
operating days. Objective: incremental net benefit (contribution, not revenue).
Candidates with negative net are never forced (holding budget is always feasible).
Deterministic: exact MILP (zero gap) on integer-cent coefficients, lexicographic tie-break
(max net, then min cost, then earliest candidate id).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from optimization.action_catalog import (
    BUDGET_CENTS,
    MAX_ACTION_TYPES,
    SelectedAction,
    price_selection,
)
from optimization.investment_model import (
    ADMISSIBLE,
    ASSUMPTION_REQUIRED,
    Economics,
    InvestmentModel,
    economics,
)

MODE_EVIDENCE = "evidence_supported"
MODE_CONDITIONAL = "conditional"


@dataclass
class Portfolio:
    allocation: dict[str, int]  # candidate_id -> quantity (only > 0)
    net_benefit: float
    total_cost: float
    mode: str
    excluded: dict[str, str] = field(default_factory=dict)
    status: str = "OPTIMAL"

    @property
    def portfolio_id(self) -> str:
        key = json.dumps(sorted(self.allocation.items()))
        return "PF-" + hashlib.sha256(key.encode()).hexdigest()[:10].upper()

    @property
    def signature(self) -> str:
        return ";".join(f"{k}x{v}" for k, v in sorted(self.allocation.items())) or "HOLD"


def admissible(e: Economics, status: str, mode: str) -> bool:
    if e.net_per_unit is None or e.max_quantity == 0:
        return False
    if mode == MODE_EVIDENCE:
        return status in ADMISSIBLE
    return status in ADMISSIBLE | {ASSUMPTION_REQUIRED}


def optimise(model: InvestmentModel, mode: str = MODE_CONDITIONAL,
             budget_cents: int = BUDGET_CENTS) -> Portfolio:
    econ = {c.candidate_id: economics(model, c) for c in model.candidates}
    cands = sorted(model.candidates, key=lambda c: c.candidate_id)
    use, excluded = [], {}
    for c in cands:
        e = econ[c.candidate_id]
        if admissible(e, e.status, mode):
            use.append(c)
        else:
            excluded[c.candidate_id] = (e.status if e.net_per_unit is None or e.status
                                        not in ADMISSIBLE | {ASSUMPTION_REQUIRED}
                                        else ("assumption-based (excluded in evidence mode)"
                                              if mode == MODE_EVIDENCE else "no operating days"))
    if not use:
        return Portfolio({}, 0.0, 0.0, mode, excluded)

    ids = [c.candidate_id for c in use]
    types = sorted({c.action_type for c in use})
    nx, ny = len(ids), len(types)
    n = nx + ny  # variables: quantities x_i (integer), then type indicators y_t (binary)
    cost = np.array([float(round(econ[i].unit_cost * 100)) for i in ids] + [0.0] * ny,
                    dtype=np.float64)
    # admissible candidates always have a numeric net (None was filtered out above)
    net = np.array([float(round((econ[i].net_per_unit or 0.0) * 100)) for i in ids]
                   + [0.0] * ny, dtype=np.float64)
    rows: list[np.ndarray] = []
    lo: list[float] = []
    hi: list[float] = []

    def row(coefs: dict[int, float], lb: float, ub: float) -> None:
        r = np.zeros(n)
        for j, v in coefs.items():
            r[j] += v
        rows.append(r)
        lo.append(lb)
        hi.append(ub)

    idx = {k: j for j, k in enumerate(ids)}
    row({j: cost[j] for j in range(nx)}, -np.inf, budget_cents)  # hard budget
    for t_i, t in enumerate(types):  # catalog quantity limit per type; y_t = type used
        members = [idx[c.candidate_id] for c in use if c.action_type == t]
        limit = model.catalog.actions[t].quantity_limit
        row({**{j: 1.0 for j in members}, nx + t_i: -limit}, -np.inf, 0)
        row({**{j: 1.0 for j in members}, nx + t_i: -1.0}, 0, np.inf)
    row({nx + t_i: 1.0 for t_i in range(ny)}, -np.inf, MAX_ACTION_TYPES)  # <= 3 types
    groups: dict[str, list[int]] = {}
    for t_i, t in enumerate(types):  # catalog incompatibility groups (not same_machine)
        g = model.catalog.actions[t].incompatibility_group
        if g and g != "same_machine":
            groups.setdefault(g, []).append(nx + t_i)
    for js in groups.values():
        row({j: 1.0 for j in js}, -np.inf, 1)
    by_machine: dict[str, list[int]] = {}  # same_machine: one move/replace per machine
    for c in use:
        if model.catalog.actions[c.action_type].incompatibility_group == "same_machine":
            for mid in c.machines:
                by_machine.setdefault(mid, []).append(idx[c.candidate_id])
    for js in by_machine.values():
        row({j: 1.0 for j in js}, -np.inf, 1)
    caps: dict[str, list[int]] = {}  # destination-slot capacity
    for c in use:
        if c.capacity_group:
            caps.setdefault(c.capacity_group, []).append(idx[c.candidate_id])
    for z, js in caps.items():
        row({j: 1.0 for j in js}, -np.inf, model.capacity.get(z, 0))
    upper = np.array([econ[i].max_quantity for i in ids] + [1] * ny, dtype=float)
    bounds = Bounds(np.zeros(n), upper)
    integrality = np.ones(n)

    def solve(objective: np.ndarray, extra: list[tuple[np.ndarray, float, float]]
              ) -> np.ndarray:
        A = np.vstack(rows + [e[0] for e in extra])
        cons = LinearConstraint(A, lo + [e[1] for e in extra], hi + [e[2] for e in extra])
        res = milp(objective, constraints=cons, integrality=integrality, bounds=bounds,
                   options={"mip_rel_gap": 0, "presolve": True, "time_limit": 30})
        if res.status != 0:
            raise RuntimeError(f"MILP status {res.status}: {res.message}")
        return np.round(res.x).astype(int)

    # Lexicographic, exact on integer-cent coefficients:
    # 1) max net; 2) min cost among those; 3) prefer earliest candidate ids
    x1 = solve(net * -1.0, [])
    best = float(net @ x1)
    x2 = solve(cost, [(net, best - 0.5, np.inf)])
    min_cost = float(cost @ x2)
    order = np.array([j + 1 for j in range(nx)] + [0] * ny, dtype=float)
    x3 = solve(order, [(net, best - 0.5, np.inf), (cost, -np.inf, min_cost + 0.5)])
    alloc = {ids[j]: int(x3[j]) for j in range(nx) if x3[j] > 0}
    return Portfolio(alloc, sum(net[idx[k]] * q for k, q in alloc.items()) / 100,
                     sum(cost[idx[k]] * q for k, q in alloc.items()) / 100, mode, excluded)


def evaluate(model: InvestmentModel, alloc: dict[str, int]) -> tuple[float, float, bool]:
    """Re-evaluate a fixed allocation under (possibly different) model inputs.

    Returns (net benefit, cost, feasible). Uses unrounded economics; blocked or
    inadmissible components contribute nothing and make the result infeasible.
    """
    by_id = {c.candidate_id: c for c in model.candidates}
    net = cost = 0.0
    feasible = True
    for cid, q in alloc.items():
        e = economics(model, by_id[cid])
        deliverable = min(q, e.max_quantity)  # e.g. fewer promo weekends after a delay
        cost += e.unit_cost * deliverable
        if e.net_per_unit is None or q > e.max_quantity:
            feasible = False
        if e.net_per_unit is None:
            continue
        net += e.net_per_unit * deliverable
    if cost > BUDGET_CENTS / 100 + 1e-9:
        feasible = False
    return net, cost, feasible


def verify(model: InvestmentModel, p: Portfolio) -> list[str]:
    """Independent re-check with the Step 1 catalog validator and direct re-summation."""
    problems = []
    by_id = {c.candidate_id: c for c in model.candidates}
    sel = [SelectedAction(action_type_id=by_id[k].action_type, quantity=q, extra_cost_cents=0,
                          targets=by_id[k].machines * q if by_id[k].machines else [])
           for k, q in p.allocation.items()]
    if model.cost_multiplier == 1.0 and model.lead_delay_days == 0:
        priced = price_selection(model.catalog, sel)
        if not priced.valid:
            problems.append(f"catalog validator: {priced.violations}")
        if abs(priced.total_usd - p.total_cost) > 0.01:
            problems.append(f"cost mismatch {priced.total_usd} vs {p.total_cost}")
    net, cost, feasible = evaluate(model, p.allocation)
    if abs(net - p.net_benefit) > 0.01 * max(1, len(p.allocation)):
        problems.append(f"net mismatch {net:.2f} vs {p.net_benefit:.2f}")
    if not feasible:
        problems.append("allocation infeasible on re-evaluation")
    if p.total_cost > BUDGET_CENTS / 100:
        problems.append("over budget")
    return problems
