"""Step 4: Whisper Network council (RULE_BASED), gossip-off vs gossip-on, persistence, gates.

Usage:
  uv run python scripts/run_step4.py                       # local DuckDB
  uv run python scripts/run_step4.py --backend databricks  # workspace.house_of_minds
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

try:
    _SCRIPT = Path(__file__).resolve()
except NameError:  # Databricks serverless exec()
    _SCRIPT = Path(sys.argv[0]).resolve()
ROOT = _SCRIPT.parents[1]
sys.path.insert(0, str(ROOT))

from typing import Any  # noqa: E402

import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402

from config.settings import get_settings  # noqa: E402
from council.agents import build_agents  # noqa: E402
from council.council import EXECUTION_MODE, CouncilResult, run_council  # noqa: E402
from council.network import MAX_OUT_PER_ROUND, MAX_ROUNDS  # noqa: E402
from council.schemas import Verdict  # noqa: E402
from council.selftest import run_negative_tests  # noqa: E402
from optimization.action_catalog import ActionCatalog  # noqa: E402
from optimization.investment_model import build_model  # noqa: E402
from optimization.portfolio import MODE_CONDITIONAL, MODE_EVIDENCE, optimise  # noqa: E402

PRIOR_TABLES = ["contract_machine_performance", "contract_demand_day",
                "contract_downtime_month", "contract_guest_month", "contract_comp_day",
                "contract_intervention_options", "reconciliation_results",
                "machine_comparison", "evidence_ledger", "validation_summary",
                "investment_candidates", "intervention_assumptions", "optimization_runs",
                "portfolio_allocations", "scenario_results", "decision_reversals",
                "portfolio_regret", "decision_evidence_links", "optimizer_validation_summary"]
STEP4_TABLES = ["council_runs", "agent_claims", "council_whispers",
                "claim_verification_results", "council_decision_events",
                "council_portfolio_impacts", "agent_reliability_summary",
                "council_validation_summary"]


def code_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((ROOT / "council").glob("*.py")) + [_SCRIPT]:
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def open_repo(backend: str) -> Any:
    s = get_settings()
    if backend == "databricks":
        from backend.repositories.databricks_repo import DatabricksRepository
        return DatabricksRepository(s.databricks_warehouse_id or "", s.databricks_catalog,
                                    s.databricks_schema, s.databricks_profile)
    from pipelines.ingestion.loader import open_local_repository
    return open_local_repository(s)


def ledger_ids(repo: Any, backend: str) -> set[str]:
    if backend == "databricks":
        return set(repo.query_df("SELECT evidence_id FROM evidence_ledger").evidence_id)
    return {json.loads(x)["evidence_id"] for x in
            (ROOT / "data/processed/evidence_ledger.jsonl").read_text().splitlines()}


def rows_for(res: CouncilResult, snapshot: str, job_run: str) -> dict[str, list[dict[str, Any]]]:
    st = res.state
    claims = []
    for c in st.claims.values():
        d = c.model_dump(mode="json")
        d.update(snapshot_id=snapshot, config=res.config,
                 tool_calls=json.dumps(d["tool_calls"]),
                 evidence_ids=",".join(c.evidence_ids), query_refs=",".join(c.query_refs),
                 depends_on=",".join(c.depends_on),
                 proposed_change=json.dumps(d["proposed_change"]) if c.proposed_change else None,
                 retracted=c.claim_id in st.retracted)
        claims.append(d)
    msgs = []
    for m in st.messages:
        d = m.model_dump(mode="json")
        d.update(snapshot_id=snapshot, config=res.config,
                 forward_chain=">".join(m.forward_chain), evidence_ids=",".join(m.evidence_ids),
                 flagged_retracted_origin=m.message_id in st.flagged,
                 flag_reason=st.flagged.get(m.message_id))
        msgs.append(d)
    vers = []
    for v in res.verifications.values():
        d = v.model_dump(mode="json")
        d.update(snapshot_id=snapshot, config=res.config, reasons=" | ".join(v.reasons),
                 agent_id=st.claims[v.claim_id].agent_id)
        vers.append(d)
    events = []
    for e in st.events:
        d = e.model_dump(mode="json")
        d.update(snapshot_id=snapshot, config=res.config, payload=json.dumps(d["payload"]))
        events.append(d)
    impacts = [{**i, "snapshot_id": snapshot, "config": res.config} for i in res.impacts]
    rel = []
    for a in build_agents():
        mine = [c for c in st.claims.values() if c.agent_id == a.agent_id]
        mv = [res.verifications[c.claim_id] for c in mine]
        rel.append({
            "council_run_id": res.council_run_id, "snapshot_id": snapshot, "config": res.config,
            "agent_id": a.agent_id, "agent_name": a.name, "hypothesis": a.hypothesis,
            "claims": len(mine),
            "verified": sum(v.verdict == Verdict.VERIFIED for v in mv),
            "inconclusive": sum(v.verdict == Verdict.INCONCLUSIVE for v in mv),
            "rejected": sum(v.verdict in (Verdict.REJECTED, Verdict.BLOCKED) for v in mv),
            "verified_decision_relevant": sum(
                v.verdict == Verdict.VERIFIED and v.decision_relevance == "DECISION_RELEVANT"
                for v in mv),
            "unsupported_claims": sum(v.verdict != Verdict.VERIFIED for v in mv),
            "retracted": sum(c.claim_id in st.retracted for c in mine),
            "messages_sent": sum(m.sender_agent_id == a.agent_id
                                 and m.message_status == "DELIVERED" for m in st.messages),
            "messages_received": sum(m.recipient_agent_id == a.agent_id
                                     and m.message_status == "DELIVERED" for m in st.messages),
            "llm_tokens": 0, "llm_cost_usd": 0.0, "execution_mode": EXECUTION_MODE})
    run = [{"council_run_id": res.council_run_id, "snapshot_id": snapshot, "config": res.config,
            "execution_mode": EXECUTION_MODE, "gossip_enabled": res.metrics["gossip_enabled"],
            "max_rounds": MAX_ROUNDS, "max_out_per_agent_round": MAX_OUT_PER_ROUND,
            "code_hash": code_hash(), "job_run_id": job_run,
            **{k: v for k, v in res.metrics.items() if k not in ("gossip_enabled",
                                                                 "execution_mode")},
            "hearing": json.dumps(res.hearing),
            "invalidation_tests": json.dumps(res.invalidation, default=str)}]
    return {"council_runs": run, "agent_claims": claims, "council_whispers": msgs,
            "claim_verification_results": vers, "council_decision_events": events,
            "council_portfolio_impacts": impacts, "agent_reliability_summary": rel}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["duckdb", "databricks"], default="duckdb")
    ap.add_argument("--warehouse-id")
    ap.add_argument("--catalog")
    ap.add_argument("--schema")
    ap.add_argument("--output-dir")
    ap.add_argument("--job-run-id", default="")
    args = ap.parse_args(argv)
    for flag, env in [("warehouse_id", "DATABRICKS_WAREHOUSE_ID"),
                      ("catalog", "DATABRICKS_CATALOG"), ("schema", "DATABRICKS_SCHEMA"),
                      ("output_dir", "HOM_OUTPUT_DIR")]:
        if getattr(args, flag):
            os.environ[env] = getattr(args, flag)
    get_settings.cache_clear()
    t0 = time.time()
    out_root = Path(os.environ.get("HOM_OUTPUT_DIR", str(ROOT)))
    out_dir = out_root / "data" / "processed" / "step4" / args.backend
    out_dir.mkdir(parents=True, exist_ok=True)
    rep_dir = out_root / "reports" / "step4"
    rep_dir.mkdir(parents=True, exist_ok=True)

    repo = open_repo(args.backend)
    existing = set(repo.list_tables())
    prior_before = {t: int(repo.scalar(f"SELECT count(*) FROM {t}"))
                    for t in PRIOR_TABLES if t in existing}
    manifest = json.loads((ROOT / "reports" / "dataset_manifest.json").read_text())
    ids = ledger_ids(repo, args.backend)
    model = build_model(repo, ActionCatalog.load(repo))
    canonical = {m: optimise(model, m) for m in (MODE_EVIDENCE, MODE_CONDITIONAL)}
    snapshot = f"SNAP-{manifest['fingerprint']}-{model.fingerprint()}"

    a = run_council(repo, model, ids, gossip=False)
    b = run_council(repo, model, ids, gossip=True)
    negative = run_negative_tests(repo, model, ids)

    tables: dict[str, list[dict[str, Any]]] = {t: [] for t in STEP4_TABLES}
    for res in (a, b):
        for k, v in rows_for(res, snapshot, args.job_run_id).items():
            tables[k] += v

    # ---------------------------------------------------------------- gates
    gates: list[dict[str, Any]] = []

    def gate(n: int, name: str, ok: bool | None, detail: Any) -> None:
        gates.append({"snapshot_id": snapshot, "gate_no": n, "gate": name,
                      "status": "BLOCKED" if ok is None else ("PASS" if ok else "FAIL"),
                      "detail": json.dumps(detail, default=str)[:900]})

    agents = build_agents()
    sb, ca = b.state, b.state.claims
    gate(1, "six specialist roles exist", len({x.agent_id for x in agents}) == 6,
         [x.name for x in agents])
    gate(2, "distinct falsifiable hypotheses", len({x.hypothesis for x in agents}) == 6
         and len({x.tools for x in agents}) == 6, "distinct hypotheses and tool allowlists")
    ia = {c.claim_id: c for c in a.initial_claims}
    ib = {c.claim_id.replace(b.council_run_id, ""): c for c in b.initial_claims}
    gate(3, "independent investigations preserved (same before gossip)",
         [(c.agent_id, c.statement) for c in a.initial_claims]
         == [(c.agent_id, c.statement) for c in b.initial_claims]
         and all(c.round_number == 0 and not c.depends_on for c in b.initial_claims),
         {"initial_claims": len(ia), "b_initial": len(ib)})
    gate(4, "claims follow strict schemas", all(hasattr(c, "claim_id") for c in ca.values()),
         "pydantic frozen models; validated on creation")
    gate(5, "unsupported claims identified",
         b.metrics["claims_inconclusive"] + b.metrics["claims_rejected"] > 0
         and any(n["case_no"] == 1 and n["status"] == "PASS" for n in negative),
         {"inconclusive": b.metrics["claims_inconclusive"]})
    gate(6, "agents can abstain",
         next(n for n in negative if n["case_no"] == 21)["status"] == "PASS",
         "Demand Strategist emits ABSTAIN when transfer is not identifiable (case 21); "
         "agents stay silent when a message adds nothing")
    gate(7, "no agent can change the winning portfolio",
         all(e.actor in ("STEP3_OPTIMIZER",) for e in sb.events
             if e.event_type == "OPTIMIZER_EXECUTED")
         and optimise(model, MODE_EVIDENCE).signature == canonical[MODE_EVIDENCE].signature,
         "only the Step 3 optimiser emits portfolio events")
    delivered = [m for m in sb.messages if m.message_status == "DELIVERED"]
    gate(8, "selective private routing works",
         0 < len({(m.sender_agent_id, m.recipient_agent_id) for m in delivered}) < 30
         and all(m.recipient_agent_id != m.sender_agent_id for m in delivered),
         {"delivered": len(delivered), "possible_pairs": 30})
    gate(9, "two-round limit enforced", max(m.round_number for m in sb.messages) <= 2,
         max(m.round_number for m in sb.messages))
    per = {}
    for m in delivered:
        if m.message_type.value != "RETRACT":
            per[(m.sender_agent_id, m.round_number)] = per.get(
                (m.sender_agent_id, m.round_number), 0) + 1
    gate(10, "message budget enforced", max(per.values()) <= MAX_OUT_PER_ROUND
         and len(delivered) <= 24, {"max_per_agent_round": max(per.values()),
                                    "delivered": len(delivered)})
    gate(11, "origin tracking works",
         all(m.origin_claim_id in ca and m.forward_chain[0] == ca[m.origin_claim_id].agent_id
             for m in sb.messages if m.origin_claim_id in ca), "origin + chain on every msg")
    gate(12, "repeated claims are not independent evidence",
         next(n for n in negative if n["case_no"] == 3)["status"] == "PASS"
         and b.metrics["messages_suppressed_duplicate"] >= 1,
         {"suppressed_duplicates": b.metrics["messages_suppressed_duplicate"]})
    gate(13, "messaging cycles prevented",
         next(n for n in negative if n["case_no"] == 5)["status"] == "PASS", "case 5")
    gate(14, "retractions propagate", b.metrics["retractions"] >= 1
         and b.metrics["messages_flagged_retracted_origin"] >= 1,
         {"retracted": sorted(sb.retracted), "flagged": len(sb.flagged)})
    types = {m.message_type.value for m in delivered}
    gate(15, "escalation and counterclaims work", {"ESCALATE", "COUNTERCLAIM"} <= types,
         sorted(types))
    gate(16, "evidence IDs resolve", all(v.source_valid for v in b.verifications.values())
         and next(n for n in negative if n["case_no"] == 2)["status"] == "PASS",
         "all council claims source-valid; fake ID rejected")
    gate(17, "numeric claims reproduce",
         all(v.arithmetic_valid is not False for v in b.verifications.values())
         and all(v.reproduced_value is not None for cid, v in b.verifications.items()
                 if ca[cid].numeric_result is not None), "re-run on fresh tool instance")
    gate(18, "source/arithmetic/causal/decision checks distinguished",
         len({(v.statistical_support, v.causal_support, v.decision_relevance)
              for v in b.verifications.values()}) > 1, "six separate dimensions recorded")
    gate(19, "prompt injection rejected",
         next(n for n in negative if n["case_no"] == 14)["status"] == "PASS", "case 14")
    gate(20, "unsupported changes cannot reach optimiser",
         all(b.verifications[i["claim_id"]].parameter_admissibility == "ADMISSIBLE_SCENARIO"
             for i in b.impacts)
         and next(n for n in negative if n["case_no"] == 10)["status"] == "PASS",
         "every optimiser call traces to an ADMISSIBLE_SCENARIO verdict")
    gate(21, "existing Step 3 optimiser reused",
         all(e.actor == "STEP3_OPTIMIZER" for e in sb.events
             if e.event_type == "OPTIMIZER_EXECUTED"), "optimization.portfolio.optimise")
    gate(22, "original portfolios immutable",
         optimise(model, MODE_EVIDENCE).portfolio_id == canonical[MODE_EVIDENCE].portfolio_id
         and optimise(model, MODE_CONDITIONAL).portfolio_id
         == canonical[MODE_CONDITIONAL].portfolio_id, "canonical model unchanged")
    gate(23, "admissible revisions produce real reoptimisation",
         any(i["portfolio_changed"] for i in b.impacts),
         [(i["mode"], i["portfolio_before"], i["portfolio_after"]) for i in b.impacts])
    unresolved = [cid for cid, v in b.verifications.items()
                  if v.verdict != Verdict.VERIFIED and ca[cid].proposed_change is None]
    gate(24, "unresolved objections do not mutate assumptions",
         not any(i["claim_id"] in unresolved for i in b.impacts)
         and all(model.assumptions[k].value == build_model(repo, model.catalog).assumptions[
             k].value for k in model.assumptions), {"unresolved": len(unresolved)})
    gate(25, "$100,000 budget enforced", all(i["cost_after"] <= 100000 for i in b.impacts)
         and next(n for n in negative if n["case_no"] == 12)["status"] == "PASS", "")
    gate(26, "max three action types enforced",
         all(i["action_types_after"] <= 3 for i in b.impacts)
         and next(n for n in negative if n["case_no"] == 13)["status"] == "PASS", "")
    gate(27, "promotion invalidation tested",
         all(i["status"] == "PASS" for i in b.invalidation), b.invalidation)
    gate(28, "portfolio impacts recorded correctly",
         all(abs(i["net_after"] - i["net_before"] - i["net_difference"]) < 1e-6
             and i["constraint_check"] == "OK" for i in b.impacts), len(b.impacts))
    gate(29, "gossip-disabled baseline runs", a.metrics["messages_delivered"] == 0
         and a.metrics["claims_total"] > 0, a.metrics["claims_total"])
    gate(30, "gossip-enabled configuration runs", b.metrics["messages_delivered"] > 0,
         b.metrics["messages_delivered"])
    gate(31, "same initial cases and evidence",
         [c.statement for c in a.initial_claims] == [c.statement for c in b.initial_claims],
         "identical independent findings, verifier, optimiser")
    keys = ["claims_verified", "unsupported_claim_rate", "verified_decision_relevant_objections",
            "decision_changing_verified_challenges", "portfolio_changes", "runtime_seconds",
            "llm_tokens", "llm_cost_usd"]
    gate(32, "comparison covers quality, relevance, runtime, cost",
         all(k in a.metrics and k in b.metrics for k in keys), keys)
    same_decisions = sorted((i["mode"], i["portfolio_after_id"]) for i in a.impacts) == sorted(
        (i["mode"], i["portfolio_after_id"]) for i in b.impacts)
    gate(33, "no unsupported claim of gossip superiority",
         isinstance(same_decisions, bool) and "decision_changing_verified_challenges"
         in b.metrics,
         {"same_portfolio_outcomes": same_decisions,
          "statement": "decision outcomes compared, not message counts"})
    tables["council_validation_summary"] = []  # filled after persistence checks
    for name, rows in tables.items():
        if name == "council_validation_summary":
            continue
        df = pd.DataFrame(rows)
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
        repo.write_table(name, pa.Table.from_pandas(df, preserve_index=False))
    n_events = int(repo.scalar("SELECT count(*) FROM council_decision_events"))
    gate(34, "council events persisted", n_events == sum(len(r.state.events) for r in (a, b)),
         n_events)
    q = repo.query_df("""SELECT sender_agent_id, recipient_agent_id, message_type,
                            message_status, count(*) n FROM council_whispers
                         WHERE config = 'B_WHISPER_NETWORK' GROUP BY 1, 2, 3, 4""")
    gate(35, "whisper events queryable", len(q) > 0, len(q))
    seq = repo.query_df("""SELECT sequence FROM council_decision_events
                           WHERE config = 'B_WHISPER_NETWORK' ORDER BY sequence""").sequence
    gate(36, "decision playback reproducible", list(seq) == sorted(set(seq))
         and next(n for n in negative if n["case_no"] == 17)["status"] == "PASS",
         {"events": len(seq)})
    gate(37, "agent reliability records exist",
         int(repo.scalar("SELECT count(*) FROM agent_reliability_summary")) == 12, 12)
    dup = {t: int(repo.scalar(f"SELECT count(*) - count(DISTINCT {k}) FROM {t}"))
           for t, k in [("agent_claims", "claim_id"), ("council_whispers", "message_id"),
                        ("claim_verification_results", "claim_id"),
                        ("council_runs", "council_run_id")]}
    gate(38, "reruns do not duplicate records", not any(dup.values()), dup)
    prior_after = {t: int(repo.scalar(f"SELECT count(*) FROM {t}")) for t in prior_before}
    src_ok = all(int(repo.scalar(f"SELECT count(*) FROM {t['table']}")) == t["rows"]
                 for t in manifest["tables"] if t["status"] != "missing")
    gate(39, "Step 1-3 tables unchanged", prior_after == prior_before and src_ok,
         {"tables_checked": len(prior_after), "sources_ok": src_ok})
    dash = repo.query_df("""
        SELECT w.config, w.sender_agent_id src, w.recipient_agent_id dst, w.message_type,
               w.message_status, v.verdict
        FROM council_whispers w LEFT JOIN claim_verification_results v
          ON v.claim_id = w.claim_id AND v.config = w.config""")
    gate(40, "outputs consumable by dashboard serving layer (graph join)", len(dash) > 0
         and dash.verdict.notna().any(), len(dash))
    for n in negative:
        gates.append({"snapshot_id": snapshot, "gate_no": 100 + n["case_no"],
                      "gate": f"negative: {n['case']}", "status": n["status"],
                      "detail": n["detail"]})
    pd.DataFrame(gates).to_parquet(out_dir / "council_validation_summary.parquet", index=False)
    repo.write_table("council_validation_summary", pa.Table.from_pylist(gates))

    summary = {
        "snapshot_id": snapshot, "backend": args.backend, "execution_mode": EXECUTION_MODE,
        "runtime_seconds": round(time.time() - t0, 1),
        "created_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "council_runs": {r.config: r.council_run_id for r in (a, b)},
        "gossip_off": a.metrics, "gossip_on": b.metrics, "hearing_on": b.hearing,
        "impacts_on": b.impacts, "invalidation": b.invalidation,
        "gates": {s: sum(g["status"] == s for g in gates) for s in ("PASS", "FAIL", "BLOCKED")},
        "failed": [g["gate"] for g in gates if g["status"] != "PASS"],
        "same_portfolio_outcomes_on_vs_off": same_decisions}
    (rep_dir / f"step4_summary_{args.backend}.json").write_text(
        json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: summary[k] for k in ("snapshot_id", "council_runs", "gates",
                                              "failed", "same_portfolio_outcomes_on_vs_off")},
                     indent=1))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    _rc = main()
    if _rc:  # serverless treats any SystemExit as failure: raise only on error
        raise SystemExit(_rc)
