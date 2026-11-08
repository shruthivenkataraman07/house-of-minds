"""Official challenge: should the manager replace the 10 lowest-earning machines?

Reuses Step 1 fair-comparison outputs (machine_comparison) and Step 3 economics
(optimization.investment_model) - no new financial formulas.

Verdict rules, applied in order to measured evidence (nothing hard-coded per machine):
  1. RETIRED_ALREADY        retire_date inside the window: no replacement decision exists.
  2. DO_NOT_REPLACE_INSPECT payout frequency inconsistent with game math (hit-rate test,
                            Bonferroni p < 0.001): the fix is an inspection.
  3. DO_NOT_REPLACE_EXPOSURE low total from limited floor time while luck-free demand per
                            available hour is not in the floor's bottom quartile.
  4. Economics of A-REPLACE-LEASE (cheapest catalog replacement, 16 operating days):
       net <= 0 even at the evidence ceiling (best title ever observed in the zone)
                         -> DO_NOT_REPLACE_NOT_ECONOMIC
       positive only above the planning value -> INSUFFICIENT_EVIDENCE
       positive at the planning value          -> REPLACE_JUSTIFIED_CONDITIONAL
Incremental benefit = (new-title rate - this machine's own rate) x hours, never the new
machine's full revenue.
"""

from __future__ import annotations

import copy
from datetime import date
from typing import Any

import pandas as pd

from analytics.machine_performance import compare_machines
from backend.repositories.base import AnalyticsRepository
from optimization.investment_model import (
    ASSUMPTION_REQUIRED,
    EV,
    Candidate,
    InvestmentModel,
    economics,
)

WINDOW_END = date(2025, 6, 30)
OFFICIAL_BOTTOM10_SQL = """
    SELECT machine_id, SUM(house_win_usd)::DOUBLE AS house_win_usd
    FROM prepared_daily_view WHERE active
    GROUP BY machine_id ORDER BY house_win_usd, machine_id LIMIT 10"""


def official_bottom10(repo: AnalyticsRepository) -> pd.DataFrame:
    """GUIDE.md definition: lowest aggregate observed house win on active days."""
    df = repo.query_df(OFFICIAL_BOTTOM10_SQL)
    df["manager_rank"] = range(1, len(df) + 1)
    return df


def machine_facts(repo: AnalyticsRepository) -> pd.DataFrame:
    """Per machine: own post-reopening theo/hour (Step 3 basis), zone, config, status."""
    return repo.query_df("""
        WITH last AS (
          SELECT machine_id, zone_id, config_id,
                 row_number() OVER (PARTITION BY machine_id ORDER BY gaming_date DESC) rk
          FROM prepared_daily_view WHERE active)
        SELECT mc.machine_id, mc.install_date, mc.retire_date, mc.lease_class,
               l.zone_id cur_zone, l.config_id cur_config,
               sum(m.theo_cents) FILTER (WHERE m.gaming_date >= DATE '2025-04-07')::DOUBLE
                 / 100 / nullif(sum(m.available_seconds) FILTER (
                   WHERE m.gaming_date >= DATE '2025-04-07') / 3600.0, 0) own_rate_recent
        FROM machines mc JOIN last l ON l.machine_id = mc.machine_id AND l.rk = 1
        LEFT JOIN machine_day m ON m.machine_id = mc.machine_id AND m.active
        GROUP BY 1, 2, 3, 4, 5, 6""")


def zone_ceilings(repo: AnalyticsRepository) -> dict[str, float]:
    """Evidence ceiling per zone (Step 3 rule generalised): best observed same-zone config
    rate, or the newest title's Center Pit rate scaled by the zone/Center Pit ratio."""
    pr = repo.query_df("""
        SELECT p.zone_id, m.config_id, sum(m.theo_cents)::DOUBLE / 100
                 / (sum(m.available_seconds) / 3600.0) rate
        FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
        WHERE m.active AND m.gaming_date >= DATE '2025-04-07' GROUP BY 1, 2""")
    zr = repo.query_df("""
        SELECT p.zone_id, sum(m.theo_cents)::DOUBLE / 100 / (sum(m.available_seconds)/3600.0) r
        FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
        WHERE m.active GROUP BY 1""").set_index("zone_id").r
    newest = float(pr[pr.config_id == "G-NEW91"].rate.max())
    out = {}
    for z in zr.index:
        best = pr[pr.zone_id == z].rate.max()
        out[z] = float(max(best, newest * zr[z] / zr["Z-PIT"]))
    return out


def with_replacement_candidates(model: InvestmentModel, facts: pd.DataFrame,
                                ceilings: dict[str, float], machine_ids: list[str]
                                ) -> InvestmentModel:
    """Copy of the canonical model plus one A-REPLACE-LEASE candidate per machine."""
    m = copy.deepcopy(model)
    f = facts.set_index("machine_id")
    existing = {c.candidate_id for c in m.candidates}
    for mid in machine_ids:
        r = f.loc[mid]
        cid = f"INV-REPLACE-LEASE-{mid}"
        if cid in existing or pd.isna(r.own_rate_recent):
            continue
        m.facts[f"replace_ceiling_rate:{mid}"] = ceilings[r.cur_zone]
        m.facts[f"replace_target_rate:{mid}"] = float(r.own_rate_recent)
        m.candidates.append(Candidate(
            cid, "A-REPLACE-LEASE", mid, 1, True, f"replacement of {mid} in {r.cur_zone}",
            ["A10_replacement_gap_capture"],
            f"{mid}: {r.own_rate_recent:.2f} $/h vs zone ceiling {ceilings[r.cur_zone]:.2f}",
            ASSUMPTION_REQUIRED, "new-title effect not identified; ceiling evidence-based",
            [EV["decomposition"]], machines=[mid]))
    return m


def lease_economics(model: InvestmentModel, mid: str) -> dict[str, float | None]:
    c = next((x for x in model.candidates if x.candidate_id == f"INV-REPLACE-LEASE-{mid}"),
             None)
    if c is None:
        return {"net_planning": None, "net_best_case": None, "cost": None}
    plan = economics(model, c)
    best = economics(model.with_assumption("A10_replacement_gap_capture", 1.0), c)
    return {"net_planning": plan.net_per_unit, "net_best_case": best.net_per_unit,
            "cost": plan.unit_cost, "gross_gain_planning": plan.gross_theo_gain}


def verdicts(repo: AnalyticsRepository, model: InvestmentModel) -> dict[str, Any]:
    cmp = compare_machines(repo)
    mc = cmp.machines.set_index("machine_id")
    b10 = official_bottom10(repo)
    facts = machine_facts(repo)
    ceil = zone_ceilings(repo)
    on_floor = facts[facts.retire_date.isna() | (pd.to_datetime(facts.retire_date)
                                                 > pd.Timestamp(WINDOW_END))].machine_id
    m2 = with_replacement_candidates(model, facts, ceil, list(on_floor))
    q1 = mc.theo_per_available_hour.quantile(0.25)
    f = facts.set_index("machine_id")
    rows = []
    for r in b10.itertuples():
        x, fr = mc.loc[r.machine_id], f.loc[r.machine_id]
        econ = lease_economics(m2, r.machine_id)
        retired = pd.notna(fr.retire_date) and pd.Timestamp(fr.retire_date) <= pd.Timestamp(
            WINDOW_END)
        gaps = {k: float(x[f"gap_{k}_usd"]) for k in
                ("luck", "exposure", "location", "game_config", "machine_residual")}
        factors = [k for k, v in sorted(gaps.items(), key=lambda kv: kv[1]) if v < -1000]
        flags = str(x.explanation)
        if retired:
            v, alt = "RETIRED_ALREADY", "none: machine left the floor on " + str(fr.retire_date)
        elif x.hit_p_bonferroni < 0.001:
            v, alt = "DO_NOT_REPLACE_INSPECT", "A-INSPECT (verify paytable / meters)"
        elif x.active_days < 150 and x.theo_per_available_hour > q1:
            v, alt = "DO_NOT_REPLACE_EXPOSURE", "none: low total reflects limited floor time"
        elif econ["net_best_case"] is not None and econ["net_best_case"] <= 0:
            v, alt = "DO_NOT_REPLACE_NOT_ECONOMIC", (
                "location/config levers (move, wayfinding) if their evidence supports them")
        elif econ["net_planning"] is not None and econ["net_planning"] <= 0:
            v, alt = "INSUFFICIENT_EVIDENCE", "measure new-title demand before replacing"
        elif econ["net_planning"] is not None:
            v, alt = "REPLACE_JUSTIFIED_CONDITIONAL", "A-REPLACE-LEASE"
        else:
            v, alt = "INSUFFICIENT_EVIDENCE", "no recent on-floor demand to compare"
        rows.append({
            "machine_id": r.machine_id, "manager_rank": r.manager_rank,
            "house_win_usd": r.house_win_usd, "theo_usd": float(x.theo_usd),
            "coin_in_usd": float(x.coin_in_usd), "payout_usd": float(x.payout_usd),
            "luck_residual_usd": float(x.luck_residual_usd), "luck_z": float(x.luck_z),
            "hit_rate_z": float(x.hit_rate_z_cfg), "hit_p_bonferroni": float(x.hit_p_bonferroni),
            "active_days": int(x.active_days), "available_hours": float(x.available_hours),
            "availability_rate": float(x.availability_rate),
            "downtime_hours": float(x.downtime_hours),
            "zone_id": x.zone_id, "config_id": x.config_id, "rtp": float(x.rtp),
            "volatility_class": x.volatility_class,
            "theo_per_available_hour": float(x.theo_per_available_hour),
            "theo_per_ah_p05": float(x.theo_per_ah_p05),
            "theo_per_ah_p95": float(x.theo_per_ah_p95),
            "zone_theo_per_available_hour": float(x.zone_theo_per_available_hour),
            "machine_vs_peer_index": float(x.machine_vs_peer_index),
            "peer_machines": int(x.peer_machines), "rank_luck_aware": int(x.rank_luck_aware),
            "rank_vs_peers": int(x.rank_vs_peers),
            "retire_date": None if pd.isna(fr.retire_date) else str(fr.retire_date),
            "install_date": str(fr.install_date),
            **{f"gap_{k}_usd": v for k, v in gaps.items()},
            "primary_factors": ",".join(factors) or "none_material",
            "analytic_flags": flags,
            "lease_cost_usd": econ["cost"], "lease_net_planning_usd": econ["net_planning"],
            "lease_net_best_case_usd": econ["net_best_case"],
            "zone_ceiling_rate": ceil.get(str(x.zone_id)),
            "verdict": v, "replacement_justified": v == "REPLACE_JUSTIFIED_CONDITIONAL",
            "recommended_alternative": alt,
            "evidence_ids": f"{EV['decomposition']},{EV['persistence']}"
                            + (f",{EV['payout_anomaly']}" if "INSPECT" in v else ""),
        })
    # floor-wide replacement opportunities (same economics)
    cands = []
    for mid in on_floor:
        e = lease_economics(m2, mid)
        if e["net_best_case"] is not None and e["net_best_case"] > 0:
            fr2 = f.loc[mid]
            cands.append({"machine_id": mid, "zone_id": fr2.cur_zone,
                          "config_id": fr2.cur_config, "own_rate": fr2.own_rate_recent,
                          "zone_ceiling_rate": ceil[fr2.cur_zone],
                          "lease_net_planning_usd": e["net_planning"],
                          "lease_net_best_case_usd": e["net_best_case"],
                          "in_manager_bottom10": mid in set(b10.machine_id)})
    cand = pd.DataFrame(cands).sort_values(["lease_net_planning_usd", "machine_id"],
                                           ascending=[False, True]) if cands else pd.DataFrame()
    return {"rows": rows, "candidates": cand, "model_with_replacements": m2,
            "bottom10": b10, "ceilings": ceil, "on_floor": list(on_floor)}


def compare_portfolios(model: InvestmentModel, m2: InvestmentModel, rows: list[dict[str, Any]]
                       ) -> list[dict[str, Any]]:
    """Manager proposal vs House of Minds vs no action, on identical Step 3 economics."""
    from optimization.action_catalog import SelectedAction, price_selection
    from optimization.portfolio import MODE_CONDITIONAL, MODE_EVIDENCE, evaluate, optimise

    by_id = {c.candidate_id: c for c in m2.candidates}
    replaceable = [r["machine_id"] for r in rows
                   if f"INV-REPLACE-LEASE-{r['machine_id']}" in by_id
                   and r["verdict"] != "RETIRED_ALREADY"]
    retired = [r["machine_id"] for r in rows if r["verdict"] == "RETIRED_ALREADY"]

    def score(name: str, alloc: dict[str, int], note: str, basis_model: InvestmentModel,
              unc: dict[str, tuple[str, float, float]] | None = None) -> dict[str, Any]:
        sel: dict[str, int] = {}
        for k, q in alloc.items():
            t = by_id[k].action_type
            sel[t] = sel.get(t, 0) + q
        priced = price_selection(m2.catalog, [SelectedAction(
            action_type_id=t, quantity=q, extra_cost_cents=0) for t, q in sel.items()])
        net, cost, feas = evaluate(basis_model, alloc)
        lo = hi = net
        for a_id, vlo, vhi in (unc or {}).values():
            lo = min(lo, evaluate(basis_model.with_assumption(a_id, vlo), alloc)[0])
            hi = max(hi, evaluate(basis_model.with_assumption(a_id, vhi), alloc)[0])
        return {"option": name, "allocation": ";".join(f"{k}x{v}" for k, v in
                                                       sorted(alloc.items())) or "HOLD",
                "action_types": len(sel), "cost_usd": priced.total_usd,
                "remaining_budget_usd": 100000 - priced.total_usd,
                "expected_incremental_contribution_usd": net + cost,
                "expected_net_benefit_usd": net, "net_low_usd": lo, "net_high_usd": hi,
                "uncertainty_basis": "; ".join(f"{a} in [{x}, {y}]" for a, x, y in
                                               (unc or {}).values()) or "n/a",
                "feasible": bool(priced.valid and feas),
                "violations": "; ".join(priced.violations), "note": note,
                "horizon": "2025-07-01..2025-07-30"}

    a10 = ("A10_replacement_gap_capture", 0.0, 1.0)
    a08 = m2.assumptions["A08_promo_excess_theo_per_day"]
    out = [
        score("manager_proposal_lease", {f"INV-REPLACE-LEASE-{m}": 1 for m in replaceable},
              f"leases for the {len(replaceable)} machines still on the floor; "
              f"{len(retired)} already retired ({', '.join(retired)}) cannot be replaced",
              m2, {"a10": a10}),
        score("house_of_minds_evidence", optimise(model, MODE_EVIDENCE).allocation,
              "evidence-supported portfolio (Step 3)", m2,
              {"a08": ("A08_promo_excess_theo_per_day", a08.low, a08.high)}),
        score("house_of_minds_conditional", optimise(model, MODE_CONDITIONAL).allocation,
              "conditional portfolio (Step 3; planning assumptions)", m2,
              {"a08": ("A08_promo_excess_theo_per_day", a08.low, a08.high)}),
        score("house_of_minds_with_replacements_allowed",
              optimise(m2, MODE_CONDITIONAL).allocation,
              "optimiser re-run with a lease-replacement option for every on-floor machine",
              m2),
        score("no_action", {}, "keep the full budget", m2),
    ]
    buy = price_selection(m2.catalog, [SelectedAction(action_type_id="A-REPLACE-BUY",
                                                      quantity=10, extra_cost_cents=0)])
    out.append({"option": "manager_proposal_buy", "allocation": "A-REPLACE-BUYx10",
                "action_types": 1, "cost_usd": buy.total_usd,
                "remaining_budget_usd": 100000 - buy.total_usd,
                "expected_incremental_contribution_usd": None,
                "expected_net_benefit_usd": None, "net_low_usd": None, "net_high_usd": None,
                "uncertainty_basis": "n/a", "feasible": bool(buy.valid),
                "violations": "; ".join(buy.violations),
                "note": "purchasing 10 machines exceeds the budget and quantity limit",
                "horizon": "2025-07-01..2025-07-30"})
    return out
