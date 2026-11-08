"""Dashboard read models over the validated contracts.

The only arithmetic here is summation of exported daily integer-cent grains followed by
ratio-of-sums; every other figure is passed through from the backend exports unchanged.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .source import DataSource

OFFICIAL = ("2025-01-01", "2025-06-30")
HORIZON = "2025-07-01..2025-07-30"
ZONE_NAMES = {
    "Z-B40": "Back Forty",
    "Z-PIT": "Center Pit",
    "Z-ENT": "Main Entrance",
    "Z-HL": "High-Limit Room",
    "Z-BAR": "Bar Row",
    "Z-GAR": "Garage Entrance",
    "Z-HTL": "Hotel Corridor",
}
AGENTS = {
    "AG1_STATISTICIAN": ("Statistician", "Luck vs signal, multiple-testing control"),
    "AG2_DEMAND": ("Demand Strategist", "Location, traffic, same-game peers"),
    "AG3_OPERATIONS": ("Operations Chief", "Exposure, downtime, payout faults"),
    "AG4_GUEST": ("Guest Analyst", "Tracked-player behavior (aggregate)"),
    "AG5_LOYALTY": ("Loyalty Strategist", "Comp cost and points economics"),
    "AG6_CFO": ("CFO", "Incremental economics, budget, regret"),
}


def _f(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- floor / bank grains
def floor_totals(src: DataSource, start: str, end: str) -> dict[str, Any]:
    ci = hw = th = cc = 0
    ah = 0.0
    days = 0
    for r in src.get("floor_day")["rows"]:
        if start <= r["d"] <= end:
            ci += r["ci"]
            hw += r["hw"]
            th += r["th"]
            cc += r["cc"]
            ah += r["ah"]
            days += 1
    return {
        "days": days,
        "coin_in_usd": ci / 100,
        "house_win_usd": hw / 100,
        "theo_usd": th / 100,
        "comp_cost_usd": cc / 100,
        "available_hours": ah,
        "hold": hw / ci if ci else None,
        "theo_hold": th / ci if ci else None,
        "coin_in_per_day_usd": ci / 100 / days if days else None,
        "coin_in_per_available_hour_usd": ci / 100 / ah if ah else None,
    }


def weekly(src: DataSource, start: str, end: str) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in src.get("floor_day")["rows"]:
        if not start <= r["d"] <= end:
            continue
        d = date.fromisoformat(r["d"])
        k = (d - timedelta(days=d.weekday())).isoformat()
        e = out.setdefault(k, {"week_start": k, "ci": 0, "th": 0, "ah": 0.0, "days": 0})
        e["ci"] += r["ci"]
        e["th"] += r["th"]
        e["ah"] += r["ah"]
        e["days"] += 1
    return [
        {
            "week_start": w["week_start"],
            "days": w["days"],
            "coin_in_usd": w["ci"] / 100,
            "theo_usd": w["th"] / 100,
            "coin_in_per_day_usd": w["ci"] / 100 / w["days"],
            "coin_in_per_available_hour_usd": w["ci"] / 100 / w["ah"] if w["ah"] else None,
        }
        for w in sorted(out.values(), key=lambda x: x["week_start"])
    ]


def bank_totals(src: DataSource, start: str, end: str, zone: str | None) -> list[dict[str, Any]]:
    bd = src.get("bank_day")
    idx = [i for i, d in enumerate(bd["dates"]) if start <= d <= end]
    rows = []
    for b in bd["banks"]:
        if zone and b["zone_id"] != zone:
            continue
        ci = sum(b["ci"][i] for i in idx)
        hw = sum(b["hw"][i] for i in idx)
        th = sum(b["th"][i] for i in idx)
        ah = sum(b["ah"][i] for i in idx)
        rows.append(
            {
                "bank_id": b["bank_id"],
                "zone_id": b["zone_id"],
                "zone_name": ZONE_NAMES.get(b["zone_id"], b["zone_id"]),
                "coin_in_usd": ci / 100,
                "house_win_usd": hw / 100,
                "theo_usd": th / 100,
                "available_hours": ah,
                "machine_days": sum(b["md"][i] for i in idx),
                "hold": hw / ci if ci else None,
                "theo_per_available_hour_usd": th / 100 / ah if ah else None,
            }
        )
    return sorted(rows, key=lambda r: r["theo_per_available_hour_usd"] or 0)


def bank_detail(src: DataSource, bank_id: str, start: str, end: str) -> dict[str, Any] | None:
    bd = src.get("bank_day")
    b = next((x for x in bd["banks"] if x["bank_id"] == bank_id), None)
    if b is None:
        return None
    daily = [
        {
            "gaming_date": d,
            "coin_in_usd": b["ci"][i] / 100,
            "house_win_usd": b["hw"][i] / 100,
            "theo_usd": b["th"][i] / 100,
        }
        for i, d in enumerate(bd["dates"])
        if start <= d <= end
    ]
    tot = next(r for r in bank_totals(src, start, end, None) if r["bank_id"] == bank_id)
    machines = [m["machine_id"] for m in src.get("machine_bank") if m["bank_id"] == bank_id]
    return {"totals": tot, "daily": daily, "machines": machines}


# ---------------------------------------------------------------- machines
def _maps(src: DataSource) -> dict[str, dict[str, Any]]:
    return {
        "inv": {r["machine_id"]: r for r in src.get("ch_machine_investigation")},
        "rob": {r["machine_id"]: r for r in src.get("audit_b4_robustness_matrix")},
        "ver": {r["machine_id"]: r for r in src.get("audit_a3_a4_verification")},
        "cand": {r["machine_id"]: r for r in src.get("ch_replacement_candidates")},
        "bank": {r["machine_id"]: r["bank_id"] for r in src.get("machine_bank")},
    }


def machine_rows(src: DataSource) -> list[dict[str, Any]]:
    mp = _maps(src)
    rows = []
    for m in src.get("dash_machine_intelligence"):
        mid = m["machine_id"]
        inv, rob, cand = mp["inv"].get(mid), mp["rob"].get(mid), mp["cand"].get(mid)
        ver = mp["ver"].get(mid)
        rows.append(
            {
                "machine_id": mid,
                "config_id": m["config_id"],
                "manufacturer": m["manufacturer"],
                "zone_id": m["zone_id"],
                "zone_name": ZONE_NAMES.get(m["zone_id"], m["zone_id"]),
                "bank_id": mp["bank"].get(mid),
                "house_win_usd": m["house_win_usd"],
                "theo_usd": m["theo_usd"],
                "theo_per_available_hour_usd": m["theo_per_available_hour"],
                "available_hours": m["available_hours"],
                "availability_rate": m["availability_rate"],
                # meter downtime for the manager's 10; otherwise scheduled - available hours,
                # where scheduled = available / availability (exported fields only)
                "downtime_hours": inv["downtime_hours"]
                if inv
                else (m["available_hours"] / m["availability_rate"] - m["available_hours"])
                if m["availability_rate"]
                else None,
                "rank_raw": m["rank_raw"],
                "rank_luck_aware": m["rank_luck_aware"],
                "rank_vs_peers": m["rank_vs_peers"],
                "luck_z": m["luck_z"],
                "hit_rate_z": m["hit_rate_z_cfg"],
                "payout_anomaly": abs(m["hit_rate_z_cfg"]) > 4.656,
                "manager_rank": inv["manager_rank"] if inv else None,
                "verdict": inv["verdict"] if inv else None,
                "lease_net_best_case_usd": (inv or cand or {}).get("lease_net_best_case_usd"),
                "robustness": rob["robustness"]
                if rob
                else (ver["classification"] if ver else None),
            }
        )
    return rows


def machine_detail(src: DataSource, mid: str) -> dict[str, Any] | None:
    m = next((x for x in src.get("dash_machine_intelligence") if x["machine_id"] == mid), None)
    if m is None:
        return None
    mp = _maps(src)
    claims = [c for c in src.get("ch_council_manager_review") if c["machine"] == mid]
    return {
        "machine": m,
        "zone_name": ZONE_NAMES.get(m["zone_id"], m["zone_id"]),
        "bank_id": mp["bank"].get(mid),
        "investigation": mp["inv"].get(mid),
        "robustness": mp["rob"].get(mid),
        "verification": mp["ver"].get(mid),
        "candidate": mp["cand"].get(mid),
        "council_claims": [
            {**c, "agent_name": AGENTS.get(c["agent_id"], (c["agent_id"],))[0]} for c in claims
        ],
    }


# ---------------------------------------------------------------- evidence passports
NR = "not recorded in the exported contracts"


def _usd(v: Any) -> str:
    x = _f(v)
    if x is None:
        return "n/a"
    s = f"${abs(x):,.0f}"
    return f"-{s}" if x < 0 else s


def passport(src: DataSource, evidence_id: str) -> dict[str, Any] | None:
    """Resolve an evidence id (passport PP-, claim CLM-, machine M-, portfolio option)."""
    eid = evidence_id.strip()
    if eid.startswith("PP-"):
        p = next((x for x in src.get("dash_decision_passports") if x["passport_id"] == eid), None)
        if not p:
            return None
        return {
            "kind": "passport",
            "id": eid,
            "title": f"{p['action_name']} · {p['target_entity']}",
            "fields": [
                ["Decision", f"{eid} (portfolio {p['portfolio_id']}, {p['portfolio_mode']})"],
                [
                    "Finding",
                    f"{p['action_name']} x{p['quantity']} at {_usd(p['unit_cost'])}: "
                    f"contribution {_usd(p['modeled_incremental_effect'])}, net {_usd(p['modeled_net_contribution'])}",
                ],
                ["Source", f"dash_decision_passports; queries {p.get('source_query_ids') or NR}"],
                [
                    "Definition",
                    p.get("financial_field_note") or "net = modeled contribution - catalog cost",
                ],
                ["Period", f"{p['decision_horizon']}; data as of {p.get('data_as_of') or NR}"],
                [
                    "Calculation",
                    f"Portfolio {p['portfolio_signature']}: cost {_usd(p['portfolio_total_cost'])}, "
                    f"remaining {_usd(p['remaining_budget'])}, net {_usd(p['portfolio_modeled_net'])}",
                ],
                ["Alternative", p.get("alternative") or NR],
                ["Assumptions", p.get("assumption_ids") or "none"],
                ["Confidence", p["effect_classification"]],
                ["Reversals", p.get("reversal_summary") or NR],
                ["Council", p.get("council_claim_ids") or "none recorded"],
                ["Limitation", p.get("limitations") or NR],
            ],
            "links": [
                c.strip()
                for c in (p.get("council_claim_ids") or "").replace(";", ",").split(",")
                if c.strip()
            ][:8],
        }
    if eid.startswith("M-"):
        m = next((x for x in src.get("ch_machine_investigation") if x["machine_id"] == eid), None)
        if not m:
            return None
        mp = _maps(src)
        r, v = mp["rob"].get(eid), mp["ver"].get(eid)
        cl = [c["claim_id"] for c in src.get("ch_council_manager_review") if c["machine"] == eid]
        return {
            "kind": "machine",
            "id": eid,
            "title": f"{eid} · {m['verdict']}",
            "fields": [
                ["Decision", f"{eid} replacement verdict"],
                ["Finding", f"{m['verdict']}. Alternative: {m['recommended_alternative']}"],
                ["Source", f"ch_machine_investigation; evidence {m.get('evidence_ids') or NR}"],
                [
                    "Definition",
                    "House win = coin-in - payout (active days); theo = coin-in x (1 - RTP); "
                    "lease net = capture x (zone ceiling - own rate) x hours x contribution factor - downtime - cost",
                ],
                [
                    "Period",
                    f"{OFFICIAL[0]}..{OFFICIAL[1]} (own rate from 2025-04-07); economics {HORIZON}",
                ],
                [
                    "Calculation",
                    f"House win {_usd(m['house_win_usd'])}, theo {_usd(m['theo_usd'])}, luck z {m['luck_z']:.2f}, "
                    f"hit-rate z {m['hit_rate_z']:.2f}, {m['active_days']} active days; lease net "
                    f"{_usd(m['lease_net_planning_usd'])} planning / {_usd(m['lease_net_best_case_usd'])} best case",
                ],
                [
                    "Alternative",
                    f"Gap: luck {_usd(m['gap_luck_usd'])}, exposure {_usd(m['gap_exposure_usd'])}, "
                    f"location {_usd(m['gap_location_usd'])}, configuration {_usd(m['gap_game_config_usd'])}",
                ],
                ["Assumptions", v["assumptions"] if v else "A10 new-title gap capture"],
                [
                    "Confidence",
                    (
                        f"{r['robustness']}: conservative {_usd(r['conservative_A10_0.25_cann_0.25'])}, "
                        f"base {_usd(r['base_A10_0.5'])}, optimistic {_usd(r['optimistic_A10_1.0'])}"
                    )
                    if r
                    else "Not an economics verdict; no sensitivity applies",
                ],
                ["Council", f"{len(cl)} claims; verdict {m['council_verdict']}"],
                [
                    "Limitation",
                    f"{'Audit: ' + v['classification'] + '. ' if v else ''}"
                    "Location, configuration and player mix are confounded; July-only horizon",
                ],
            ],
            "links": cl,
        }
    for c in src.get("dash_evidence_validation"):
        if c["claim_id"] == eid:
            return {
                "kind": "claim",
                "id": eid,
                "title": c["claim_text"],
                "fields": [
                    ["Claim", c["claim_text"]],
                    ["Decision", c["decision"]],
                    ["Source", f"{c['source_table']} · {c['query_ref']}"],
                    ["Calculation", c["result"]],
                    ["Alternative", c.get("alternative_explanation") or NR],
                    ["Assumptions", c.get("assumptions") or "none"],
                    ["Confidence", f"{c['evidence_classification']} · {c['verification_status']}"],
                    ["Sensitivity", c.get("decision_sensitivity") or NR],
                    ["Limitation", c.get("limitation") or NR],
                    ["Period", f"data as of {c['data_as_of']}"],
                ],
                "links": [],
            }
    for c in src.get("ch_council_manager_review"):
        if c["claim_id"] == eid:
            return {
                "kind": "claim",
                "id": eid,
                "title": f"{AGENTS.get(c['agent_id'], (c['agent_id'],))[0]} on {c['machine']}",
                "fields": [
                    ["Claim", c["statement"]],
                    ["Decision", f"Replace {c['machine']}?"],
                    ["Source", f"ch_council_manager_review · query {c['query_refs']}"],
                    [
                        "Calculation",
                        f"{c['numeric_result']} {c['unit']}; arithmetic "
                        f"{'reproduced' if c['arithmetic_valid'] else 'NOT reproduced'}",
                    ],
                    ["Confidence", c["verdict"]],
                    ["Council", f"{c['action']} ({c['kind']})"],
                    [
                        "Limitation",
                        "Rule-based agent; the verifier recomputes numbers, not causality",
                    ],
                ],
                "links": [c["machine"]],
            }
    for e in src.get("dash_council_activity"):
        if e.get("claim_id") == eid:
            return {
                "kind": "claim",
                "id": eid,
                "title": e["description"],
                "fields": [
                    ["Claim", e["description"]],
                    ["Source", f"dash_council_activity ({e['config']})"],
                    ["Confidence", e.get("verification_status") or NR],
                    ["Decision impact", e.get("decision_consequence") or NR],
                    ["Council", f"{e['actor']}: {e['event_type']}"],
                ],
                "links": [],
            }
    p = next((x for x in src.get("ch_portfolio_comparison") if x["option"] == eid), None)
    if p:
        return {
            "kind": "portfolio",
            "id": eid,
            "title": eid,
            "fields": [
                ["Decision", "How to spend up to $100,000 in July 2025"],
                [
                    "Finding",
                    f"{_usd(p['expected_net_benefit_usd']) if p['feasible'] else 'infeasible'} for {_usd(p['cost_usd'])}",
                ],
                ["Source", "ch_portfolio_comparison (Step 3 optimizer economics)"],
                ["Definition", "Net = modeled incremental contribution - catalog cost"],
                ["Period", p["horizon"]],
                [
                    "Calculation",
                    f"{p['allocation']}; contribution {_usd(p['expected_incremental_contribution_usd'])}",
                ],
                [
                    "Confidence",
                    f"{_usd(p['net_low_usd'])} to {_usd(p['net_high_usd'])} ({p['uncertainty_basis']})",
                ],
                ["Limitation", f"{p['note']}{'; ' + p['violations'] if p['violations'] else ''}"],
            ],
            "links": [],
        }
    return None
