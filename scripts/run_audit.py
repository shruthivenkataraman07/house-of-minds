"""Hardening audit: independent re-derivation of the replacement verdicts and robustness tests.

Read-only with respect to production tables. Writes sidecar JSON to reports/audit/.
Independent parts (A3) read the official parquet files with raw SQL and do not call
analytics.replacement; they are then compared with the production values.

Usage: uv run python scripts/run_audit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import get_settings  # noqa: E402

OUT = ROOT / "reports" / "audit"
IDS = ["M-5076", "M-1158", "M-1120", "M-1118", "M-1238", "M-1181", "M-1035", "M-1179",
       "M-1017", "M-1265"]


def one(con: duckdb.DuckDBPyConnection, sql: str) -> object:
    return con.sql(sql).fetchall()[0][0]


def independent(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, dict]:
    unit, rec, lead, down_min = con.sql(
        "SELECT unit_cost_cents, recurring_cost_cents_per_day, lead_days, downtime_minutes "
        "FROM ac WHERE action_type_id='A-REPLACE-LEASE'").fetchall()[0]
    peer = con.sql("""SELECT p.zone_id, m.config_id,
        sum(m.theo_cents)/100.0/(sum(m.available_seconds)/3600.0) r
        FROM md m JOIN pv p USING(machine_id, gaming_date)
        WHERE m.active AND m.gaming_date >= DATE '2025-04-07' GROUP BY 1, 2""").df()
    zr = con.sql("""SELECT p.zone_id, sum(m.theo_cents)/100.0/(sum(m.available_seconds)/3600.0) r
        FROM md m JOIN pv p USING(machine_id, gaming_date) WHERE m.active GROUP BY 1"""
                 ).df().set_index("zone_id").r
    newest = peer[peer.config_id == "G-NEW91"].r.max()
    ceil = {z: float(max(peer[peer.zone_id == z].r.max(), newest * zr[z] / zr["Z-PIT"]))
            for z in zr.index}
    own = con.sql(f"""
        WITH last AS (SELECT machine_id, zone_id, row_number() OVER
                      (PARTITION BY machine_id ORDER BY gaming_date DESC) rk FROM pv WHERE active)
        SELECT m.machine_id, any_value(l.zone_id) zone, any_value(c.lease_class) lease_class,
          any_value(c.retire_date) retire_date, count(*) active_days,
          sum(m.theo_cents) FILTER (WHERE m.gaming_date >= DATE '2025-04-07')/100.0
            / nullif(sum(m.available_seconds) FILTER
                     (WHERE m.gaming_date >= DATE '2025-04-07')/3600.0, 0) own,
          sum(m.theo_cents)/100.0/(sum(m.available_seconds)/3600.0) own_full,
          (sum(m.payout_positive_spins) - sum(m.paid_spins)*any_value(g.hit_probability))
            / sqrt(sum(m.paid_spins)*any_value(g.hit_probability)
                   *(1-any_value(g.hit_probability))) hit_z
        FROM md m JOIN mc c USING(machine_id) JOIN gm g ON g.config_id = m.config_id
        JOIN last l ON l.machine_id = m.machine_id AND l.rk = 1
        WHERE m.active AND m.machine_id IN {tuple(IDS)} GROUP BY 1""").df().set_index("machine_id")
    comp = float(one(con, """SELECT (SELECT sum(comp_cost_usd) FROM pd_
        WHERE gaming_date >= DATE '2025-05-01') / (SELECT sum(theo_cents)/100.0 FROM md
        WHERE active AND gaming_date >= DATE '2025-05-01')"""))
    inputs = {"lease_unit_usd": unit / 100, "lease_per_day_usd": rec / 100, "lead_days": lead,
              "downtime_minutes": down_min, "comp_cost_per_theo": comp, "zone_ceilings": ceil}
    return own, inputs


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    d = Path(get_settings().challenge_data_dir)
    con = duckdb.connect()
    for n, p in [("md", "2_machine_decision/machine_day"),
                 ("pv", "1_prepared_views/prepared_daily_view"),
                 ("mc", "2_machine_decision/machines"), ("gm", "2_machine_decision/game_math"),
                 ("ac", "2_machine_decision/action_catalog"),
                 ("pd_", "1_prepared_views/property_day")]:
        con.sql(f"CREATE VIEW {n} AS SELECT * FROM '{d / p}.parquet'")
    own, inp = independent(con)

    # production values, for comparison only
    from analytics.replacement import compare_portfolios, verdicts
    from optimization.action_catalog import ActionCatalog
    from optimization.investment_model import build_model, economics, effective_days
    from optimization.portfolio import MODE_CONDITIONAL, MODE_EVIDENCE, evaluate, optimise
    from pipelines.ingestion.loader import open_local_repository
    repo = open_local_repository()
    model = build_model(repo, ActionCatalog.load(repo))
    v = verdicts(repo, model)
    m2 = v["model_with_replacements"]
    prod = pd.DataFrame(v["rows"]).set_index("machine_id")
    days = effective_days(inp["lead_days"], 0)
    cf = model.facts["floor_contribution_factor"]
    cost = inp["lease_unit_usd"] + inp["lease_per_day_usd"] * days
    inp.update({"operating_days_in_horizon": days, "floor_contribution_factor": cf,
                "lease_total_usd": cost})
    q1 = float(one(con, """SELECT quantile_cont(r, 0.25) FROM (SELECT machine_id,
        sum(theo_cents)/100.0/(sum(available_seconds)/3600.0) r FROM md WHERE active
        GROUP BY 1)"""))

    # ---------------- A3/A4 independent verdicts
    a_rows, b_rows = [], []
    for mid in IDS:
        o = own.loc[mid]
        p = prod.loc[mid]
        retired = pd.notna(o.retire_date) and pd.Timestamp(o.retire_date) <= pd.Timestamp(
            "2025-06-30")
        rec = {"machine_id": mid, "zone": o.zone, "lease_class": o.lease_class,
               "retire_date": None if pd.isna(o.retire_date) else str(o.retire_date),
               "active_days": int(o.active_days), "hit_z_independent": float(o.hit_z),
               "own_theo_per_ah_full_window": float(o.own_full),
               "production_verdict": p.verdict}
        if retired:
            iv = "RETIRED_ALREADY"
        elif abs(o.hit_z) > 4.656:  # Bonferroni |z| for p<0.001 over 310 machines (Step 1)
            iv = "DO_NOT_REPLACE_INSPECT"
        else:
            gap = inp["zone_ceilings"][o.zone] - o.own
            H = 24 * days
            down = inp["downtime_minutes"] / 60 * o.own * cf

            def net(a10: float, f: float = cf, cann: float = 0.0, extra: float = 0.0,
                    gap: float = gap, H: float = H, down: float = down) -> float:
                return a10 * gap * H * f * (1 - cann) + extra - down - cost

            plan, best = net(0.5), net(1.0)
            exposure = o.active_days < 150 and o.own_full > q1
            iv = ("DO_NOT_REPLACE_EXPOSURE" if exposure else "DO_NOT_REPLACE_NOT_ECONOMIC"
                  if best <= 0 else "INSUFFICIENT_EVIDENCE" if plan <= 0
                  else "REPLACE_JUSTIFIED_CONDITIONAL")
            # lease-structure sensitivity: catalog lease is a fixed fee, so the new title carries
            # no revenue share; a replaced revenue-share machine's 20% share is saved
            cf_new = 1 - inp["comp_cost_per_theo"]
            rs_saved = 0.2 * o.own * H if o.lease_class == "leased_revenue_share" else 0.0
            ls_plan = (o.own + 0.5 * gap) * H * cf_new - o.own * H * (cf_new - (
                0.2 if rs_saved else 0)) - down - cost
            ls_best = (o.own + 1.0 * gap) * H * cf_new - o.own * H * (cf_new - (
                0.2 if rs_saved else 0)) - down - cost
            be_july = (cost + down) / (gap * H * cf)
            be_ss = inp["lease_per_day_usd"] / (gap * 24 * cf)
            rec.update({"own_theo_per_ah_post_0407": float(o.own),
                        "zone_ceiling": inp["zone_ceilings"][o.zone], "gap_per_ah": gap,
                        "net_planning_independent": plan, "net_best_independent": best,
                        "net_planning_production": p.lease_net_planning_usd,
                        "net_best_production": p.lease_net_best_case_usd,
                        "abs_diff_best": abs(best - p.lease_net_best_case_usd)})
            b_rows.append({
                "machine_id": mid, "production_verdict": p.verdict,
                "conservative_A10_0.25_cann_0.25": net(0.25, cann=0.25),
                "base_A10_0.5": plan, "optimistic_A10_1.0": best,
                "leaseclass_adjusted_planning": ls_plan, "leaseclass_adjusted_best": ls_best,
                "best_with_ceiling_+10pct": net(1.0, gap=gap + 0.1 * inp["zone_ceilings"][o.zone]),
                "breakeven_A10_july": be_july,
                "steady_state_breakeven_A10": be_ss,
                "steady_state_daily_net_at_A10_0.5": 0.5 * gap * 24 * cf - inp["lease_per_day_usd"],
                "payback_days_after_install_at_A10_0.5":
                    (inp["lease_unit_usd"] + down)
                    / (0.5 * gap * 24 * cf - inp["lease_per_day_usd"]),
                "robustness": (
                    "ROBUST" if max(best, ls_best, net(1.0, gap=gap + 0.1 * inp[
                        "zone_ceilings"][o.zone])) <= 0 else
                    "CONDITIONAL" if p.verdict != "INSUFFICIENT_EVIDENCE" else
                    "INSUFFICIENT EVIDENCE"),
                "horizon_note": ("not economic within Jul 1-30 at every tested value; "
                                 "steady-state payback exists only if A10 >= "
                                 f"{be_ss:.2f}") if be_ss < 1 else
                                "not economic even in steady state at A10<=1"})
        rec["independent_verdict"] = iv
        rec["classification"] = ("DISAGREEMENT" if iv != p.verdict else "VERIFIED" if iv in (
            "RETIRED_ALREADY", "DO_NOT_REPLACE_INSPECT") else "VERIFIED WITH ASSUMPTIONS")
        rec["assumptions"] = {
            "RETIRED_ALREADY": "none (machines.retire_date)",
            "DO_NOT_REPLACE_INSPECT": "game_math hit probability is the true paytable value",
        }.get(iv, "zone ceiling = best observed title; 16 lease days (catalog: lease runs for "
                  "remainder of horizon); floor-average contribution factor; A10 <= 1")
        a_rows.append(rec)
    a = pd.DataFrame(a_rows)
    b = pd.DataFrame(b_rows)

    # ---------------- C: promotion and portfolio robustness
    a08 = m2.assumptions["A08_promo_excess_theo_per_day"]
    ev = optimise(model, MODE_EVIDENCE).allocation
    cd = optimise(model, MODE_CONDITIONAL).allocation
    promo_ids = [k for k in ev if "PROMO" in k]
    no_promo_model = __import__("copy").deepcopy(model)
    no_promo_model.candidates = [c for c in no_promo_model.candidates
                                 if c.action_type != "A-PROMO"]
    s5 = json.loads((ROOT / "reports/step5/step5_summary_duckdb.json").read_text())
    scen = {"zero_uplift": 0.0, "weakest_event": a08.low, "base_mean": a08.value,
            "strongest_event": a08.high}
    be = None
    lo_, hi_ = 0.0, a08.high
    for _ in range(60):
        mid_ = (lo_ + hi_) / 2
        if evaluate(model.with_assumption(a08.key if hasattr(a08, "key") else
                                          "A08_promo_excess_theo_per_day", mid_),
                    {k: ev[k] for k in promo_ids})[0] > 0:
            hi_ = mid_
        else:
            lo_ = mid_
    be = hi_
    scen["break_even"] = be
    pe = s5.get("per_event_excess")
    c_rows = []
    for name, val in scen.items():
        m = model.with_assumption("A08_promo_excess_theo_per_day", val)
        r = {"scenario": name, "A08": val}
        for label, alloc in [("original_evidence", ev), ("original_conditional", cd),
                             ("evidence_without_promo",
                              {k: q for k, q in ev.items() if k not in promo_ids}),
                             ("conditional_without_promo",
                              {k: q for k, q in cd.items() if "PROMO" not in k}),
                             ("promo_only", {k: ev[k] for k in promo_ids})]:
            r[label] = evaluate(m, alloc)[0]
        r["reoptimised_conditional_choice"] = ";".join(
            f"{k}x{q}" for k, q in sorted(optimise(m, MODE_CONDITIONAL).allocation.items()))
        c_rows.append(r)
    reopt = {mode: optimise(no_promo_model, mode) for mode in (MODE_EVIDENCE, MODE_CONDITIONAL)}
    comp = compare_portfolios(model, m2, v["rows"])
    c_summary = {
        "promotion_ids": promo_ids, "a08": {"low": a08.low, "value": a08.value, "high": a08.high},
        "minus_1506_meaning": "total evidence-portfolio net at A08 = weakest observed event "
                              f"({a08.low:.2f}/day); a scenario value, not a confidence bound",
        "break_even_A08": be, "step5_per_event_excess": pe,
        "scenarios": c_rows,
        "reoptimised_promo_prohibited": {k: {"allocation": p.allocation,
                                             "net": evaluate(no_promo_model, p.allocation)[0]}
                                         for k, p in reopt.items()},
        "manager_and_no_action": [{k: c[k] for k in ("option", "cost_usd",
                                                     "expected_net_benefit_usd", "net_low_usd",
                                                     "net_high_usd", "feasible")}
                                  for c in comp]}

    # action classification across tested scenarios
    act_cls = {}
    for k in sorted(set(ev) | set(cd)):
        nets = [evaluate(model.with_assumption("A08_promo_excess_theo_per_day", val),
                         {k: (ev | cd)[k]})[0] for val in scen.values()]
        e = economics(model, next(c for c in model.candidates if c.candidate_id == k))
        act_cls[k] = {"status": e.status, "net_by_A08_scenario": nets}
    c_summary["action_nets"] = act_cls

    # ---------------- D: stored council / forecast evidence
    s5p = ROOT / "data/processed/step5/duckdb"
    abl = pd.read_parquet(s5p / "council_ablation_results.parquet")
    dmi = pd.read_parquet(s5p / "decision_model_impact.parquet")
    fbc = pd.read_parquet(s5p / "forecast_baseline_comparison.parquet")
    gates = pd.read_parquet(s5p / "step5_validation_summary.parquet")
    d_summary = {"council_ablation": json.loads(abl.to_json(orient="records")),
                 "decision_model_impact": json.loads(dmi.to_json(orient="records")),
                 "forecast_baseline_comparison": json.loads(fbc.to_json(orient="records")),
                 "step5_gates_stored": {"rows": len(gates), "status_counts": gates.iloc[:, :].
                                        filter(like="status").stack().value_counts().to_dict()}}

    (OUT / "a3_a4_verification.json").write_text(a.to_json(orient="records", indent=1))
    (OUT / "b4_robustness_matrix.json").write_text(b.to_json(orient="records", indent=1))
    (OUT / "b_inputs.json").write_text(json.dumps(inp, indent=1, default=float))
    (OUT / "c_promotion_portfolio.json").write_text(json.dumps(c_summary, indent=1,
                                                               default=str))
    (OUT / "d_council_forecast.json").write_text(json.dumps(d_summary, indent=1, default=str))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(json.dumps(inp, default=float, indent=0))
    print(a.round(3).to_string(index=False))
    print(b.round(3).T.to_string())
    print(json.dumps({k: v for k, v in c_summary.items() if k != "action_nets"}, indent=1,
                     default=str)[:6000])
    print(json.dumps(act_cls, indent=0, default=str))
    print(abl.to_string()[:3000])
    print(dmi.to_string()[:3000])
    print(fbc.to_string()[:2000])
    print(d_summary["step5_gates_stored"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
