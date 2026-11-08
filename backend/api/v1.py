"""Dashboard API v1: read-only, validated, snapshot-consistent."""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Response

from backend.schemas.api import (
    AskRequest,
    AskResponse,
    BankDetail,
    BankList,
    BottomMachine,
    Comps,
    CouncilDecision,
    CouncilSummary,
    Demand,
    Downtime,
    Envelope,
    EvidenceList,
    EvidencePassport,
    Executive,
    Forecast,
    Health,
    MachineDetail,
    MachinePage,
    Meta,
    Metadata,
    Players,
    Portfolios,
    Scenarios,
)
from backend.services import dashboard as d
from backend.services.ask import ask as route_question
from backend.services.source import DataSource, DataUnavailable, get_source

router = APIRouter(prefix="/api/v1")
DateStr = Annotated[str, Query(pattern=r"^2025-(0[1-6])-(0[1-9]|[12]\d|3[01])$")]
Zone = Annotated[str | None, Query(pattern=r"^Z-[A-Z0-9]{2,4}$")]
CACHE = "public, max-age=300"


def _meta(src: DataSource, names: list[str], period: str | None = None) -> Meta:
    m = src.snapshot.meta()
    return Meta(
        snapshot_id=m["snapshot_id"],
        data_mode=src.mode,  # type: ignore[arg-type]
        served_from=src.provenance(names),  # type: ignore[arg-type]
        exported_at_utc=m["exported_at_utc"],
        period=period,
        sources=names,
    )


def _period(start: str, end: str) -> dict[str, str]:
    if start > end:
        raise HTTPException(422, "start must be on or before end")
    return {"start": start, "end": end}


def _cached(resp: Response) -> None:
    resp.headers["Cache-Control"] = CACHE


@router.get("/health", response_model=Health)
def health() -> Health:
    src = get_source()
    try:
        snap = src.snapshot.meta()["snapshot_id"]
    except DataUnavailable as e:
        raise HTTPException(503, f"snapshot unavailable: {e}") from e
    err = src.live.last_error if src.live else None
    return Health(
        status="degraded" if err else "ok", data_mode=src.mode, snapshot_id=snap, live_error=err
    )


@router.get("/metadata", response_model=Metadata)
def metadata(resp: Response) -> Metadata:
    src = get_source()
    m = src.snapshot.meta()
    _cached(resp)
    return Metadata(
        snapshot_id=m["snapshot_id"],
        exported_at_utc=m["exported_at_utc"],
        sidecar_snapshot_id=m["sidecar_snapshot_id"],
        sidecar_exported_at_utc=m["sidecar_exported_at_utc"],
        verified_files=m["files"],
        data_mode=src.mode,
        live=src.mode == "databricks",
        note="Validated snapshot (not live)"
        if src.mode == "snapshot"
        else "Live Unity Catalog reads with snapshot fallback per dataset",
    )


@router.get("/executive", response_model=Envelope[Executive])
def executive(resp: Response) -> Any:
    src = get_source()
    v = src.get("ch_executive_verdict")[0]
    b10 = sorted(src.get("ch_machine_investigation"), key=lambda m: m["manager_rank"])
    cand = src.get("ch_replacement_candidates")
    cr = src.get("ch_council_manager_review")
    pa = src.get("audit_c_promotion_portfolio")
    insp = next(
        (
            p["unit_cost"]
            for p in src.get("dash_decision_passports")
            if p["action_type_id"] == "A-INSPECT"
        ),
        None,
    )
    names = [
        "ch_executive_verdict",
        "ch_machine_investigation",
        "ch_portfolio_comparison",
        "ch_replacement_candidates",
        "ch_council_manager_review",
        "dash_executive_kpis",
        "audit_c_promotion_portfolio",
        "dash_decision_passports",
    ]
    data = Executive(
        verdict=v,
        portfolios=src.get("ch_portfolio_comparison"),
        bottom10=[
            BottomMachine(**{**m, "retire_date": m["retire_date"] and str(m["retire_date"])[:10]})
            for m in b10
        ],
        kpis={str(k["kpi"]): float(k["value"]) for k in src.get("dash_executive_kpis")},
        promotion={
            "break_even": pa["break_even_A08"],
            "a08": pa["a08"],
            "scenarios": {s["scenario"]: s["original_evidence"] for s in pa["scenarios"]},
        },
        council_claims=len(cr),
        council_verified=sum(c["verdict"] == "VERIFIED" for c in cr),
        floor_candidates=len(cand),
        floor_planning_positive=sum(c["lease_net_planning_usd"] > 0 for c in cand),
        floor_best_case_positive=sum(
            c["lease_net_best_case_usd"] > 0 and not c["in_manager_bottom10"] for c in cand
        ),
        inspection_cost_usd=insp,
    )
    _cached(resp)
    return {"meta": _meta(src, names), "data": data}


@router.get("/machines", response_model=Envelope[MachinePage])
def machines(
    resp: Response,
    scope: Annotated[str, Query(pattern="^(bottom10|all)$")] = "bottom10",
    sort: Annotated[str, Query(pattern="^(observed|fair|opportunity)$")] = "observed",
    zone: Zone = None,
    bank: Annotated[str | None, Query(pattern=r"^B-\d{1,3}$")] = None,
    q: Annotated[str | None, Query(max_length=40)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=310)] = 50,
) -> Any:
    src = get_source()
    rows = d.machine_rows(src)
    if scope == "bottom10":
        rows = [r for r in rows if r["manager_rank"] is not None]
    if zone:
        rows = [r for r in rows if r["zone_id"] == zone]
    if bank:
        rows = [r for r in rows if r["bank_id"] == bank]
    if q:
        ql = q.lower()
        rows = [
            r
            for r in rows
            if ql in r["machine_id"].lower()
            or ql in r["config_id"].lower()
            or ql in (r["bank_id"] or "").lower()
        ]
    key = {
        "observed": lambda r: r["rank_raw"],
        "fair": lambda r: r["rank_vs_peers"],  # 1 = weakest vs comparable machines
        "opportunity": lambda r: (
            -(r["lease_net_best_case_usd"] if r["lease_net_best_case_usd"] is not None else -1e9)
        ),
    }[sort]
    rows.sort(key=key)
    _cached(resp)
    return {
        "meta": _meta(
            src,
            [
                "dash_machine_intelligence",
                "ch_machine_investigation",
                "audit_b4_robustness_matrix",
                "machine_bank",
            ],
            "official window",
        ),
        "data": {
            "total": len(rows),
            "offset": offset,
            "limit": limit,
            "rows": rows[offset : offset + limit],
        },
    }


@router.get("/machines/{machine_id}", response_model=Envelope[MachineDetail])
def machine(resp: Response, machine_id: Annotated[str, Path(pattern=r"^M-\d{4}$")]) -> Any:
    src = get_source()
    det = d.machine_detail(src, machine_id)
    if det is None:
        raise HTTPException(404, f"machine {machine_id} not found")
    _cached(resp)
    return {
        "meta": _meta(
            src,
            [
                "dash_machine_intelligence",
                "ch_machine_investigation",
                "ch_council_manager_review",
                "audit_b4_robustness_matrix",
                "machine_bank",
            ],
            "official window",
        ),
        "data": det,
    }


@router.get("/operations/demand", response_model=Envelope[Demand])
def demand(resp: Response, start: DateStr = d.OFFICIAL[0], end: DateStr = d.OFFICIAL[1]) -> Any:
    src = get_source()
    per = _period(start, end)
    _cached(resp)
    return {
        "meta": _meta(
            src, ["floor_day", "ch_zone_demand", "ch_demand_explanations"], f"{start}..{end}"
        ),
        "data": {
            "period": per,
            "exploratory": (start, end) != d.OFFICIAL,
            "totals": d.floor_totals(src, start, end),
            "weekly": d.weekly(src, start, end),
            "daily": d.daily(src, start, end),
            "zone_monthly": [
                {**r, "zone_name": d.ZONE_NAMES.get(r["zone_id"], r["zone_id"])}
                for r in src.get("ch_zone_demand")
            ],
            "explanations": src.get("ch_demand_explanations"),
        },
    }


@router.get("/operations/banks", response_model=Envelope[BankList])
def banks(
    resp: Response, start: DateStr = d.OFFICIAL[0], end: DateStr = d.OFFICIAL[1], zone: Zone = None
) -> Any:
    src = get_source()
    per = _period(start, end)
    _cached(resp)
    return {
        "meta": _meta(src, ["bank_day"], f"{start}..{end}"),
        "data": {
            "period": per,
            "exploratory": (start, end) != d.OFFICIAL,
            "banks": d.bank_totals(src, start, end, zone),
        },
    }


@router.get("/operations/banks/{bank_id}", response_model=Envelope[BankDetail])
def bank(
    resp: Response,
    bank_id: Annotated[str, Path(pattern=r"^B-\d{1,3}$")],
    start: DateStr = d.OFFICIAL[0],
    end: DateStr = d.OFFICIAL[1],
) -> Any:
    src = get_source()
    per = _period(start, end)
    det = d.bank_detail(src, bank_id, start, end)
    if det is None:
        raise HTTPException(404, f"bank {bank_id} not found")
    _cached(resp)
    return {
        "meta": _meta(src, ["bank_day", "machine_bank"], f"{start}..{end}"),
        "data": {"bank_id": bank_id, "period": per, **det},
    }


@router.get("/operations/downtime", response_model=Envelope[Downtime])
def downtime(resp: Response) -> Any:
    src = get_source()
    by: dict[str, dict[str, float]] = {}
    for r in src.get("ch_downtime_economics"):
        e = by.setdefault(
            r["manufacturer"],
            {
                "downtime_hours": 0,
                "scheduled_hours": 0,
                "theo_at_risk_usd": 0,
                "contribution_at_risk_usd": 0,
                "faults": 0,
            },
        )
        for k in e:
            e[k] += float(r[k] or 0)
    rows: list[dict[str, Any]] = [
        {"manufacturer": k, **e, "downtime_rate": e["downtime_hours"] / e["scheduled_hours"]}
        for k, e in sorted(by.items(), key=lambda kv: -kv[1]["downtime_hours"])
    ]
    tot: dict[str, float] = {
        k: float(sum(r[k] for r in rows))
        for k in (
            "downtime_hours",
            "scheduled_hours",
            "theo_at_risk_usd",
            "contribution_at_risk_usd",
            "faults",
        )
    }
    tot["availability"] = 1 - tot["downtime_hours"] / tot["scheduled_hours"]
    _cached(resp)
    return {
        "meta": _meta(src, ["ch_downtime_economics", "ch_downtime_by_hour"], "official window"),
        "data": {
            "totals": tot,
            "by_manufacturer": rows,
            "by_hour": src.get("ch_downtime_by_hour"),
            "by_zone_month": [
                {**r, "zone_name": d.ZONE_NAMES.get(r["zone_id"], r["zone_id"])}
                for r in src.get("ch_downtime_economics")
            ],
        },
    }


@router.get("/players/summary", response_model=Envelope[Players])
def players(resp: Response) -> Any:
    src = get_source()
    _cached(resp)
    return {
        "meta": _meta(src, ["ch_player_outcomes", "ch_player_outcomes_by_tier"], "official window"),
        "data": {
            "summary": src.get("ch_player_outcomes")[0],
            "tiers": src.get("ch_player_outcomes_by_tier"),
        },
    }


@router.get("/loyalty/comps", response_model=Envelope[Comps])
def comps(resp: Response) -> Any:
    src = get_source()
    _cached(resp)
    return {
        "meta": _meta(src, ["ch_loyalty_comps"], "official window"),
        "data": {"months": src.get("ch_loyalty_comps")},
    }


@router.get("/council", response_model=Envelope[CouncilSummary])
def council(resp: Response) -> Any:
    src = get_source()
    cr = src.get("ch_council_manager_review")
    ev = src.get("dash_council_activity")
    agents = []
    for aid, (name, role) in d.AGENTS.items():
        mine = [c for c in cr if c["agent_id"] == aid]
        agents.append(
            {
                "agent_id": aid,
                "name": name,
                "role": role,
                "manager_claims": len(mine),
                "manager_verified": sum(c["verdict"] == "VERIFIED" for c in mine),
                "portfolio_findings": sum(
                    e["actor"] == aid
                    and e["event_type"] in ("INDEPENDENT_FINDING", "GOSSIP_FINDING")
                    for e in ev
                ),
                "retractions": sum(
                    e["actor"] == aid and e["event_type"] == "CLAIM_RETRACTED" for e in ev
                ),
            }
        )
    b10 = sorted(src.get("ch_machine_investigation"), key=lambda m: m["manager_rank"])
    _cached(resp)
    return {
        "meta": _meta(src, ["ch_council_manager_review", "dash_council_activity"]),
        "data": {
            "agents": agents,
            "decisions": [
                {"decision_id": "manager-proposal", "label": "Manager replacement proposal"},
                {"decision_id": "A_NO_GOSSIP", "label": "$100K hearing: independent agents"},
                {"decision_id": "B_WHISPER_NETWORK", "label": "$100K hearing: Whisper Network"},
            ],
            "machines": [
                {
                    k: m[k]
                    for k in (
                        "machine_id",
                        "manager_rank",
                        "verdict",
                        "council_verdict",
                        "council_agrees",
                        "council_deciding_claims",
                    )
                }
                for m in b10
            ],
            "claims": [
                {**c, "agent_name": d.AGENTS.get(c["agent_id"], (c["agent_id"],))[0]} for c in cr
            ],
        },
    }


@router.get("/council/{decision_id}", response_model=Envelope[CouncilDecision])
def council_decision(
    resp: Response, decision_id: Annotated[str, Path(pattern="^(A_NO_GOSSIP|B_WHISPER_NETWORK)$")]
) -> Any:
    src = get_source()
    ev = sorted(
        (e for e in src.get("dash_council_activity") if e["config"] == decision_id),
        key=lambda e: e["sequence"],
    )
    wh = [w for w in src.get("council_whispers") if w["config"] == decision_id]
    # Scenario re-runs may change the optimal plan under a tested assumption; the adopted plan
    # changes only if a revision was admitted without preserving the baseline.
    flips = [
        str(e["description"])
        for e in ev
        if e["event_type"] == "OPTIMIZER_EXECUTED"
        and e.get("portfolio_before")
        and e["portfolio_before"] != e.get("portfolio_after")
    ]
    changed = any(
        e["event_type"] == "CHANGE_ADMITTED" and "baseline preserved" not in str(e["description"])
        for e in ev
    )
    _cached(resp)
    return {
        "meta": _meta(src, ["dash_council_activity", "council_whispers"]),
        "data": {
            "decision_id": decision_id,
            "events": ev,
            "whispers": wh,
            "portfolio_changed": changed,
            "scenario_flips": flips,
        },
    }


@router.get("/portfolios", response_model=Envelope[Portfolios])
def portfolios(resp: Response) -> Any:
    src = get_source()
    pf = src.get("ch_portfolio_comparison")
    pp = src.get("dash_decision_passports")
    ev = [p for p in pp if p["portfolio_mode"] == "evidence_supported"]
    cd = [p for p in pp if p["portfolio_mode"] == "conditional"]
    cost = sum(p["total_cost"] for p in ev)
    buy = next((p for p in pf if p["option"] == "manager_proposal_buy"), None)
    constraints = [
        {
            "check": "Budget ≤ $100,000",
            "pass": cost <= 100000 and all(p["cost_usd"] <= 100000 for p in pf if p["feasible"]),
            "detail": f"${cost:,.0f} recommended",
        },
        {
            "check": "≤ 3 action types",
            "pass": len({p["action_type_id"] for p in ev}) <= 3
            and len({p["action_type_id"] for p in cd}) <= 3,
            "detail": f"{len({p['action_type_id'] for p in ev})} recommended · "
            f"{len({p['action_type_id'] for p in cd})} conditional",
        },
        {
            "check": "Promotion quantity ≤ 2",
            "pass": all(p["quantity"] <= 2 for p in pp if p["action_type_id"] == "A-PROMO"),
            "detail": "catalog limit",
        },
        {
            "check": "Horizon Jul 1–30, 2025",
            "pass": all(p["decision_horizon"] == d.HORIZON for p in pp),
            "detail": "lead days deducted before benefits accrue",
        },
        {
            "check": "Manager buy ×10",
            "pass": bool(buy and buy["feasible"]),
            "detail": f"${buy['cost_usd']:,.0f} exceeds budget" if buy else "n/a",
        },
    ]
    pa = src.get("audit_c_promotion_portfolio")
    _cached(resp)
    return {
        "meta": _meta(
            src,
            [
                "ch_portfolio_comparison",
                "dash_decision_passports",
                "measurement_plans",
                "audit_c_promotion_portfolio",
            ],
            d.HORIZON,
        ),
        "data": {
            "options": pf,
            "passports": pp,
            "measurement_plans": src.get("measurement_plans"),
            "promotion": pa,
            "constraints": constraints,
            "catalog": src.get("action_catalog"),
        },
    }


@router.get("/scenarios", response_model=Envelope[Scenarios])
def scenarios(resp: Response) -> Any:
    src = get_source()
    s = src.get("dash_scenario_surface")
    _cached(resp)
    return {
        "meta": _meta(
            src,
            ["dash_scenario_surface", "audit_c_promotion_portfolio", "audit_b_inputs"],
            d.HORIZON,
        ),
        "data": {
            "promotion": src.get("audit_c_promotion_portfolio"),
            "stress": [r for r in s if r["row_type"] == "scenario"],
            "reversals": [r for r in s if r["row_type"] == "reversal"],
            "lease_operating_days": src.get("audit_b_inputs").get("operating_days_in_horizon"),
        },
    }


@router.get("/evidence", response_model=Envelope[EvidenceList])
def evidence(
    resp: Response,
    q: Annotated[str | None, Query(max_length=60)] = None,
    category: Annotated[str | None, Query(pattern="^[a-z_]{1,40}$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> Any:
    src = get_source()
    cl = src.get("dash_evidence_validation")
    rows = [
        c
        for c in cl
        if (not category or c["category"] == category)
        and (not q or q.lower() in (c["claim_id"] + c["claim_text"]).lower())
    ]
    _cached(resp)
    return {
        "meta": _meta(src, ["dash_evidence_validation", "dash_decision_passports"]),
        "data": {
            "total": len(rows),
            "claims": rows[:limit],
            "classifications": dict(Counter(c["evidence_classification"] for c in cl)),
            "passports": [
                {k: p[k] for k in ("passport_id", "action_name", "portfolio_mode", "target_entity")}
                for p in src.get("dash_decision_passports")
            ],
            "machines": [
                m["machine_id"]
                for m in sorted(
                    src.get("ch_machine_investigation"), key=lambda m: m["manager_rank"]
                )
            ],
            "verification": src.get("audit_a3_a4_verification"),
        },
    }


@router.get("/evidence/{evidence_id}", response_model=Envelope[EvidencePassport])
def evidence_item(
    resp: Response, evidence_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_\-]{2,60}$")]
) -> Any:
    src = get_source()
    p = d.passport(src, evidence_id)
    if p is None:
        raise HTTPException(404, f"no evidence passport for {evidence_id}")
    _cached(resp)
    return {
        "meta": _meta(
            src, ["dash_decision_passports", "dash_evidence_validation", "ch_machine_investigation"]
        ),
        "data": p,
    }


@router.get("/forecast/validation", response_model=Envelope[Forecast])
def forecast(resp: Response) -> Any:
    src = get_source()
    fc = src.get("forecast_baseline_comparison")
    a = next(f for f in fc if f["subset"] == "all")
    _cached(resp)
    return {
        "meta": _meta(
            src,
            ["forecast_baseline_comparison", "dash_model_evaluation", "decision_model_impact"],
            "holdout 2025-05-01..2025-06-30",
        ),
        "data": {
            "comparison": fc,
            "holdout": sorted(src.get("dash_model_evaluation"), key=lambda r: r["gaming_date"]),
            "decision_impact": [
                r for r in src.get("decision_model_impact") if r["mode"] == "evidence_supported"
            ],
            "protocol": {
                k: a.get(k)
                for k in (
                    "protocol_version",
                    "protocol_sha256",
                    "job_run_id",
                    "source_snapshot",
                    "code_hash",
                )
            }
            | {
                "train": "2025-01-01..2025-03-31",
                "validate": "2025-04-01..2025-04-30",
                "holdout": "2025-05-01..2025-06-30",
                "model": "Holt-Winters (statsmodels)",
                "baseline": "weekday mean",
                "registry": "Delta tables (no MLflow model)",
            },
        },
    }


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest) -> Any:
    return route_question(body.question, get_source(), body.machine_context)
