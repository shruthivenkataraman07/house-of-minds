"""Submission QA: recompute key quantities from the raw official parquet files and compare them
with the public (or local) API. Independent of the dashboard code path.

Usage: uv run python scripts/qa_parity.py [BASE_URL]
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "dashboard-royale" / "data"
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://house-of-minds.onrender.com").rstrip("/")


def api(path: str) -> dict:
    req = urllib.request.Request(f"{BASE}/api/v1{path}", headers={"User-Agent": "hom-qa"})
    return json.loads(urllib.request.urlopen(req, timeout=90).read())


con = duckdb.connect()
pv = RAW / "1_prepared_views" / "prepared_daily_view.parquet"
pdy = RAW / "1_prepared_views" / "property_day.parquet"
pp = RAW / "1_prepared_views" / "player_period.parquet"
rows: list[tuple[str, str, object, object, bool]] = []


def check(name: str, src: str, expected: object, got: object, tol: float = 0.01) -> None:
    if isinstance(expected, (int, float)) and isinstance(got, (int, float)):
        ok = abs(float(expected) - float(got)) <= tol
    else:
        ok = expected == got
    rows.append((name, src, expected, got, ok))


# 1. manager bottom 10 (GUIDE query semantics: sum house win on active days)
raw_b10 = [
    r[0]
    for r in con.sql(f"""SELECT machine_id FROM '{pv}' WHERE active
    GROUP BY 1 ORDER BY sum(house_win_usd), machine_id LIMIT 10""").fetchall()
]
ex = api("/executive")["data"]
check(
    "Bottom-10 order",
    "prepared_daily_view (raw)",
    raw_b10,
    [m["machine_id"] for m in ex["bottom10"]],
)
raw_hw = {
    r[0]: float(r[1])
    for r in con.sql(f"""SELECT machine_id, sum(house_win_usd) FROM '{pv}'
    WHERE active GROUP BY 1""").fetchall()
}
check(
    "Bottom-10 house win (max abs diff)",
    "prepared_daily_view (raw)",
    0.0,
    max(abs(raw_hw[m["machine_id"]] - m["house_win_usd"]) for m in ex["bottom10"]),
)

# 2. fair performance: theo per available hour for all 310 machines
raw_rate = {
    r[0]: float(r[1])
    for r in con.sql(f"""SELECT machine_id,
    sum(theo_usd)/sum(available_hours) FROM '{pv}' WHERE active GROUP BY 1""").fetchall()
}
ms = api("/machines?scope=all&limit=310")["data"]["rows"]
check("Machines returned", "API", 310, len(ms), 0)
check(
    "Theo per available hour (max abs diff, 310 machines)",
    "prepared_daily_view (raw)",
    0.0,
    max(abs(raw_rate[m["machine_id"]] - m["theo_per_available_hour_usd"]) for m in ms),
    0.005,
)
fair = api("/machines?scope=all&sort=fair&limit=3")["data"]["rows"]
check("Fair sort starts at weakest (rank 1)", "API", 1, fair[0]["rank_vs_peers"], 0)

# 3. March 2025 demand (ratio of sums)
ci, hw, th, ah, days = con.sql(f"""SELECT sum(coin_in_usd), sum(house_win_usd), sum(theo_usd),
    sum(available_machine_hours), count(*) FROM '{pdy}'
    WHERE gaming_date BETWEEN DATE '2025-03-01' AND DATE '2025-03-31'""").fetchall()[0]
mar = api("/operations/demand?start=2025-03-01&end=2025-03-31")["data"]
t = mar["totals"]
check("March days", "property_day (raw)", 31, t["days"], 0)
check("March amount wagered", "property_day (raw)", float(ci), t["coin_in_usd"])
check("March casino win", "property_day (raw)", float(hw), t["house_win_usd"])
check("March hold (ratio of sums)", "property_day (raw)", float(hw) / float(ci), t["hold"], 1e-12)
check(
    "March per available hour",
    "property_day (raw)",
    float(ci) / float(ah),
    t["coin_in_per_available_hour_usd"],
    1e-6,
)
d15 = con.sql(
    f"""SELECT coin_in_usd FROM '{pdy}' WHERE gaming_date = DATE '2025-03-15'"""
).fetchall()[0][0]
check(
    "March 15 daily wagered (drill-down value)",
    "property_day (raw)",
    float(d15),
    next(r["coin_in_usd"] for r in mar["daily"] if r["gaming_date"] == "2025-03-15"),
)
check("March flagged exploratory", "API", True, mar["exploratory"])

# 4. downtime
dt = api("/operations/downtime")["data"]["totals"]
md = RAW / "2_machine_decision" / "machine_day.parquet"
raw_down = con.sql(
    f"SELECT sum(scheduled_seconds - available_seconds) / 3600.0 FROM '{md}'"
).fetchall()[0][0]
check(
    "Downtime hours (scheduled - available meter seconds)",
    "machine_day (raw)",
    float(raw_down),
    dt["downtime_hours"],
    0.01,
)

# 5. tracked players
pl = api("/players/summary")["data"]["summary"]
cols = [c[0] for c in con.sql(f"DESCRIBE SELECT * FROM '{pp}'").fetchall()]
cin = next((c for c in cols if "coin_in" in c), None)
if cin:
    raw_ci = con.sql(f"SELECT sum({cin}) FROM '{pp}'").fetchall()[0][0]
    check(
        "Tracked wagers",
        f"player_period.{cin} (raw)",
        float(raw_ci),
        pl["tracked_coin_in_usd"],
        1.0,
    )
check(
    "Tracked net = payouts - wagers",
    "API identity",
    pl["tracked_payout_usd"] - pl["tracked_coin_in_usd"],
    pl["tracked_player_net_usd"],
    0.05,
)

# 6. comps
cp = api("/loyalty/comps")["data"]["months"]
raw_cc = con.sql(f"SELECT sum(comp_cost_usd) FROM '{pdy}'").fetchall()[0][0]
check(
    "Comp cost Jan-Jun",
    "property_day.comp_cost_usd (raw)",
    float(raw_cc),
    sum(m["comp_cost_usd"] for m in cp),
    1.0,
)

# 7. council
co = api("/council")["data"]
check(
    "Council claims verified",
    "ch_council_manager_review",
    len(co["claims"]),
    sum(c["verdict"] == "VERIFIED" for c in co["claims"]),
    0,
)
check(
    "Council verdict = analytic verdict (all 10)",
    "ch_machine_investigation",
    10,
    sum(m["council_verdict"] == m["verdict"] for m in co["machines"]),
    0,
)

# 8. portfolio
pf = api("/portfolios")["data"]
rec = next(o for o in pf["options"] if o["option"] == ex["verdict"]["recommended_option"])
check(
    "Recommended net = verdict export",
    "ch_executive_verdict",
    ex["verdict"]["recommended_net_usd"],
    rec["expected_net_benefit_usd"],
)
check(
    "Passport lines sum to plan cost",
    "dash_decision_passports",
    rec["cost_usd"],
    sum(p["total_cost"] for p in pf["passports"] if p["portfolio_mode"] == "evidence_supported"),
)
check(
    "All feasible plans <= $100,000",
    "ch_portfolio_comparison",
    True,
    all(o["cost_usd"] <= 100000 for o in pf["options"] if o["feasible"]),
)
check(
    "All feasible plans <= 3 action types",
    "ch_portfolio_comparison",
    True,
    all(o["action_types"] <= 3 for o in pf["options"] if o["feasible"]),
)
check(
    "Over-budget plan marked infeasible",
    "ch_portfolio_comparison",
    False,
    next(o for o in pf["options"] if o["cost_usd"] > 100000)["feasible"],
)

# 9. forecast
fc = api("/forecast/validation")["data"]
snap = json.loads((ROOT / "web/public/data/current/dash_model_evaluation.json").read_text())
check("Holdout rows", "dash_model_evaluation", len(snap), len(fc["holdout"]), 0)
check(
    "Holdout starts after training/validation",
    "protocol",
    True,
    min(r["gaming_date"] for r in fc["holdout"])[:10] >= "2025-05-01",
)
check(
    "No missing predictions",
    "dash_model_evaluation",
    0,
    sum(r["candidate_pred"] is None for r in fc["holdout"]),
    0,
)
raw_theo = {
    str(r[0]): float(r[1])
    for r in con.sql(f"""SELECT gaming_date, theo_usd FROM '{pdy}'
    WHERE gaming_date >= DATE '2025-05-01'""").fetchall()
}
check(
    "Holdout actual = raw daily theo (max abs diff)",
    "property_day (raw)",
    0.0,
    max(abs(raw_theo[r["gaming_date"][:10]] - r["actual"]) for r in fc["holdout"]),
    0.01,
)

# snapshot consistency
meta = api("/metadata")
check(
    "Single snapshot across export + sidecar",
    "manifests",
    meta["snapshot_id"],
    meta["sidecar_snapshot_id"],
)
check("Labelled not live", "metadata", False, meta["live"])

w = max(len(r[0]) for r in rows)
for name, src, e, g, ok in rows:
    print(
        f"{'PASS' if ok else 'FAIL'}  {name:<{w}}  expected={str(e)[:60]}  got={str(g)[:60]}  [{src}]"
    )
print(f"{sum(r[4] for r in rows)}/{len(rows)} parity checks passed against {BASE}")
sys.exit(0 if all(r[4] for r in rows) else 1)
