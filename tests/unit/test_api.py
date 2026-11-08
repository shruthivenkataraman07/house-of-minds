"""Dashboard API v1: contracts, validation, parity, Ask the House and source fallback."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import source as srcmod
from backend.services.source import DataSource, DataUnavailable, Live

c = TestClient(app)
pytestmark = pytest.mark.skipif(
    not (srcmod.DATA / "current" / "manifest.json").exists(), reason="snapshot export not present"
)


def get(path: str) -> dict:
    r = c.get(path)
    assert r.status_code == 200, (path, r.text[:300])
    return r.json()


def test_health_and_metadata_report_snapshot_not_live():
    h = get("/api/v1/health")
    assert h["status"] == "ok" and h["snapshot_id"].startswith("chf-v1:")
    m = get("/api/v1/metadata")
    assert m["data_mode"] == "snapshot" and m["live"] is False and "not live" in m["note"]
    assert m["sidecar_snapshot_id"] == m["snapshot_id"]


def test_every_response_carries_meta_with_units_and_window():
    for p in [
        "/api/v1/executive",
        "/api/v1/machines",
        "/api/v1/operations/downtime",
        "/api/v1/portfolios",
        "/api/v1/forecast/validation",
    ]:
        meta = get(p)["meta"]
        assert (
            meta["served_from"] == "snapshot"
            and meta["official_window"] == "2025-01-01..2025-06-30"
        )
        assert meta["decision_horizon"] == "2025-07-01..2025-07-30" and "USD" in meta["units"]


def test_executive_matches_exports():
    d = get("/api/v1/executive")["data"]
    pf = {p["option"]: p for p in d["portfolios"]}
    assert d["verdict"]["answer"] == "REPLACE_NONE"
    assert pf[d["verdict"]["recommended_option"]]["expected_net_benefit_usd"] == pytest.approx(
        d["verdict"]["recommended_net_usd"]
    )
    assert [m["manager_rank"] for m in d["bottom10"]] == list(range(1, 11))


def test_period_filter_is_ratio_of_sums_and_reconciles():
    full = get("/api/v1/operations/demand")["data"]
    k = get("/api/v1/executive")["data"]["kpis"]
    assert full["totals"]["days"] == 181 and not full["exploratory"]
    assert full["totals"]["house_win_usd"] == pytest.approx(k["house_win_usd"], abs=0.01)
    assert full["totals"]["hold"] == pytest.approx(k["observed_hold"], rel=1e-9)
    may = get("/api/v1/operations/demand?start=2025-05-01&end=2025-06-30")["data"]
    assert may["exploratory"] and may["totals"]["days"] == 61
    banks = get("/api/v1/operations/banks?start=2025-05-01&end=2025-06-30")["data"]["banks"]
    assert sum(b["house_win_usd"] for b in banks) == pytest.approx(
        may["totals"]["house_win_usd"], abs=0.01
    )
    # verdicts are frozen: the executive payload is unaffected by the filter
    assert get("/api/v1/executive")["data"]["verdict"]["answer"] == "REPLACE_NONE"


def test_bank_and_machine_lookups():
    b = get("/api/v1/operations/banks/B-38")["data"]
    assert b["machines"] and b["daily"]
    m = get("/api/v1/machines/M-5076")["data"]
    assert m["investigation"]["verdict"] == "INSUFFICIENT_EVIDENCE" and m["robustness"]
    page = get("/api/v1/machines?scope=all&limit=20&offset=20")["data"]
    assert page["total"] == 310 and len(page["rows"]) == 20


@pytest.mark.parametrize(
    "path,code",
    [
        ("/api/v1/machines/M-9999", 404),
        ("/api/v1/machines/DROP", 422),
        ("/api/v1/operations/banks/B-999", 404),
        ("/api/v1/operations/demand?start=2025-07-01", 422),
        ("/api/v1/operations/demand?start=2025-06-01&end=2025-05-01", 422),
        ("/api/v1/machines?limit=5000", 422),
        ("/api/v1/evidence/NOPE-123", 404),
        ("/api/v1/council/anything", 422),
        ("/api/v1/unknown", 404),
    ],
)
def test_invalid_inputs_return_consistent_errors(path, code):
    r = c.get(path)
    assert r.status_code == code
    body = r.json()
    assert set(body) == {"error", "detail", "recovery"}


def test_read_only_no_write_methods():
    for p in ["/api/v1/machines", "/api/v1/executive", "/api/v1/ask"]:
        assert c.delete(p).status_code in (404, 405)
        assert c.put(p, json={}).status_code in (404, 405)


def test_evidence_resolves_for_every_reference():
    ex = get("/api/v1/executive")["data"]
    for m in ex["bottom10"]:
        assert get(f"/api/v1/evidence/{m['machine_id']}")["data"]["fields"]
    pf = get("/api/v1/portfolios")["data"]
    for p in pf["passports"]:
        assert get(f"/api/v1/evidence/{p['passport_id']}")["data"]["kind"] == "passport"
    for o in pf["options"]:
        assert get(f"/api/v1/evidence/{o['option']}")["data"]["kind"] == "portfolio"
    for cl in get("/api/v1/council")["data"]["claims"]:
        assert get(f"/api/v1/evidence/{cl['claim_id']}")["data"]["kind"] == "claim"


def test_portfolio_constraints_and_horizon():
    pf = get("/api/v1/portfolios")["data"]
    for o in pf["options"]:
        if o["feasible"]:
            assert o["cost_usd"] <= 100000 and o["action_types"] <= 3
            assert o["horizon"] == "2025-07-01..2025-07-30"
    checks = {x["check"]: x["pass"] for x in pf["constraints"]}
    assert checks["Budget ≤ $100,000"] and not checks["Manager buy ×10"]


ASK = [
    ("Why shouldn't we replace the original bottom 10?", "OK", "get_evidence"),
    ("Investigate machine M-1158", "OK", "select_entity"),
    ("Explain M-5076 sensitivity", "OK", "select_entity"),
    ("Compare the manager's plan with House of Minds", "OK", "compare_portfolios"),
    ("What happens if promotional uplift is zero?", "OK", "explain_reversal"),
    ("Why did the council challenge this action?", "OK", "open_council"),
    ("What happened to demand across zones?", "OK", "set_filters"),
    ("Which machines are affected by downtime?", "OK", "set_filters"),
    ("How reliable is the forecast?", "OK", "open_validation"),
    ("Explain machine M-9999", "UNAVAILABLE", None),
    ("Why is this machine low?", "AMBIGUOUS", None),
    ("What's the weather in Houston?", "UNSUPPORTED", None),
    ("SELECT * FROM players; DROP TABLE machine_day", "REFUSED", None),
    ("Delete the verdict data for M-5076", "REFUSED", None),
    ("Which loyalty groups account for tracked play?", "OK", "set_filters"),
    ("Show the evidence for this recommendation", "OK", "get_evidence"),
    ("Who are the biggest losers we should target?", "REFUSED", None),
]


@pytest.mark.parametrize("q,status,intent", ASK)
def test_ask_routes(q, status, intent):
    r = c.post("/api/v1/ask", json={"question": q})
    assert r.status_code == 200
    a = r.json()
    assert a["status"] == status
    if intent:
        assert a["intent"] == intent


def test_ask_context_premise_and_figures():
    a = c.post(
        "/api/v1/ask", json={"question": "Why is this machine low?", "machine_context": "M-5076"}
    ).json()
    assert a["status"] == "OK" and a["action"]["args"]["machine_id"] == "M-5076"
    assert (
        "did not reject"
        in c.post(
            "/api/v1/ask", json={"question": "Why did the council reject the promotion plan?"}
        ).json()["premise_correction"]
    )
    z = c.post("/api/v1/ask", json={"question": "What if promo uplift is zero?"}).json()
    assert "30,000" in z["conclusion"]
    m = c.post("/api/v1/ask", json={"question": "Explain machine M-5076"}).json()
    assert "Conservative".lower() in (m["uncertainty"] or "").lower()
    assert c.post("/api/v1/ask", json={"question": "x" * 500}).status_code == 422
    assert (
        c.post("/api/v1/ask", json={"question": "hi", "machine_context": "DROP"}).status_code == 422
    )


def test_live_failure_falls_back_to_snapshot_and_is_labelled():
    def broken():
        raise RuntimeError("warehouse unreachable")

    s = DataSource("databricks", Live(broken))
    rows = s.get("ch_executive_verdict")
    assert rows[0]["answer"] == "REPLACE_NONE"
    assert s.served_from["ch_executive_verdict"] == "snapshot"
    assert s.live is not None and "warehouse unreachable" in (s.live.last_error or "")


def test_live_reads_only_allowlisted_tables():
    calls = []

    class Repo:
        def query_df(self, sql):
            import pandas as pd

            calls.append(sql)
            return pd.DataFrame([{"answer": "REPLACE_NONE"}])

    live = Live(lambda: Repo())
    assert live.get("ch_executive_verdict")[0]["answer"] == "REPLACE_NONE"
    live.get("ch_executive_verdict")  # cached
    assert calls == ["SELECT * FROM ch_executive_verdict"]
    with pytest.raises(DataUnavailable):
        live.get("players; DROP TABLE x")


def test_openapi_lists_v1_routes():
    spec = get("/openapi.json")
    assert {
        "/api/v1/ask",
        "/api/v1/executive",
        "/api/v1/machines/{machine_id}",
        "/api/v1/evidence/{evidence_id}",
        "/api/v1/forecast/validation",
    } <= set(spec["paths"])


def test_bank_filter_and_downtime_field():
    page = get("/api/v1/machines?scope=all&bank=B-38&limit=100")["data"]
    assert page["total"] > 0 and all(r["bank_id"] == "B-38" for r in page["rows"])
    m = next(r for r in page["rows"] if r["machine_id"] == "M-5076")
    assert m["downtime_hours"] == pytest.approx(6.0)  # metered value for a manager-list machine
    assert c.get("/api/v1/machines?bank=DROP").status_code == 422


def test_council_hearing_reports_adopted_plan_not_scenario_reruns():
    h = get("/api/v1/council/B_WHISPER_NETWORK")["data"]
    assert h["portfolio_changed"] is False  # revisions were admitted as scenarios only
    assert any(f.startswith("evidence_supported") for f in h["scenario_flips"])


def test_ask_routes_to_answers_and_catalog_has_lead_days():
    a = c.post("/api/v1/ask", json={"question": "Show the six answers"}).json()
    assert a["action"] == {"type": "open_answers", "view": "answers", "args": {}}
    cat = {x["action_type_id"]: x for x in get("/api/v1/portfolios")["data"]["catalog"]}
    assert cat["A-PROMO"]["lead_days"] == 14 and cat["A-REPLACE-LEASE"]["lead_days"] == 14


@pytest.mark.parametrize(
    "q,view,arg",
    [
        ("Show why M-5076 is conditional", "machines", ("machine_id", "M-5076")),
        ("What if promotion uplift is zero?", "scenarios", ("scenario", "zero_uplift")),
        ("Summarize all six challenge questions", "answers", None),
        ("Which bank has the most downtime?", "operations", ("tab", "downtime")),
        ("Show me the evidence for this investment", "evidence", None),
    ],
)
def test_ask_navigates_to_visual_evidence(q, view, arg):
    a = c.post("/api/v1/ask", json={"question": q}).json()
    assert a["status"] == "OK" and a["action"]["view"] == view
    if arg:
        assert a["action"]["args"][arg[0]] == arg[1]


def test_bank_question_states_grain_limit_and_daily_demand_present():
    a = c.post("/api/v1/ask", json={"question": "Which bank has the most downtime?"}).json()
    assert "recorded by zone, not bank" in a["support"][0]
    d = get("/api/v1/operations/demand?start=2025-03-01&end=2025-03-31")["data"]
    assert len(d["daily"]) == 31 and d["exploratory"]
    assert sum(r["coin_in_usd"] for r in d["daily"]) == pytest.approx(
        d["totals"]["coin_in_usd"], abs=0.01
    )
    assert get("/api/v1/executive")["data"]["verdict"]["answer"] == "REPLACE_NONE"
    assert len(get("/api/v1/operations/downtime")["data"]["by_zone_month"]) == 126


def test_fair_sort_lists_weakest_vs_peers_first():
    rows = get("/api/v1/machines?scope=all&sort=fair&limit=5")["data"]["rows"]
    assert [r["rank_vs_peers"] for r in rows] == [
        1,
        2,
        3,
        4,
        5,
    ]  # 1 = weakest vs comparable machines


def test_impossible_calendar_date_rejected():
    r = c.get("/api/v1/operations/demand?start=2025-02-30&end=2025-02-30")
    assert r.status_code == 422 and "not a valid calendar date" in r.json()["detail"]


def _copy_snapshot(tmp_path):
    import shutil

    shutil.copytree(srcmod.DATA / "current", tmp_path / "current")
    shutil.copytree(srcmod.DATA / "sidecar", tmp_path / "sidecar")
    return srcmod.Snapshot(root=tmp_path)


def test_snapshot_rejects_tampered_file(tmp_path):
    snap = _copy_snapshot(tmp_path)
    p = tmp_path / "current" / "ch_executive_verdict.json"
    p.write_text(p.read_text().replace("REPLACE_NONE", "REPLACE_ALL"))
    with pytest.raises(DataUnavailable, match="checksum"):
        snap.get("ch_executive_verdict")


def test_snapshot_refuses_mixed_versions(tmp_path):
    import json as _json

    snap = _copy_snapshot(tmp_path)
    mf = tmp_path / "sidecar" / "manifest.json"
    m = _json.loads(mf.read_text())
    m["snapshot_id"] = "chf-v1:other"
    mf.write_text(_json.dumps(m))
    with pytest.raises(DataUnavailable, match="does not match"):
        snap.get("floor_day")
    assert snap.get("ch_executive_verdict")[0]["answer"] == "REPLACE_NONE"  # export itself intact


def test_snapshot_missing_manifest_is_unavailable(tmp_path):
    snap = srcmod.Snapshot(root=tmp_path)
    with pytest.raises(DataUnavailable, match="manifest missing"):
        snap.get("ch_executive_verdict")


def test_optimizer_constraints_reject_infeasible_fixtures():
    from optimization.action_catalog import ActionCatalog, SelectedAction, price_selection
    from pipelines.ingestion.loader import open_local_repository

    cat = ActionCatalog.load(open_local_repository())
    over = price_selection(
        cat, [SelectedAction(action_type_id="A-REPLACE-BUY", quantity=10, extra_cost_cents=0)]
    )
    assert not over.valid and any("budget" in v for v in over.violations)
    many = price_selection(
        cat,
        [
            SelectedAction(action_type_id=a, quantity=1, extra_cost_cents=0)
            for a in ("A-INSPECT", "A-MOVE-MACHINE", "A-SURVEY", "A-COMP-CHANGE")
        ],
    )
    assert not many.valid
    too_many_promos = price_selection(
        cat, [SelectedAction(action_type_id="A-PROMO", quantity=3, extra_cost_cents=0)]
    )
    assert not too_many_promos.valid


def test_ask_month_demand_and_business_wording():
    a = c.post("/api/v1/ask", json={"question": "Show March 2025 demand."}).json()
    assert a["action"]["args"] == {"tab": "demand", "start": "2025-03-01", "end": "2025-03-31"}
    t = get("/api/v1/operations/demand?start=2025-03-01&end=2025-03-31")["data"]["totals"]
    assert f"{t['coin_in_usd']:,.0f}" in a["conclusion"]
    verb = c.post("/api/v1/ask", json={"question": "Results may show demand changes"}).json()
    assert "start" not in (verb["action"] or {}).get("args", {})
    for q in [
        "Should we replace the bottom 10 machines?",
        "Explain the $100,000 investment recommendation.",
    ]:
        text = c.post("/api/v1/ask", json={"question": q}).json()["conclusion"]
        assert "REPLACE_" not in text and "INV-" not in text and "_" not in text.split("(")[0]
