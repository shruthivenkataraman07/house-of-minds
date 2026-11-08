"""Council orchestration: independent investigations -> (optional) Whisper Network ->
deterministic verification -> hearing -> admissible changes -> existing Step 3 optimiser.

Agents never pick portfolios. Only claims whose proposed change is ADMISSIBLE_SCENARIO
reach the optimiser, as versioned scenario assumption sets; the Step 3 baselines are
never modified.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from council.agents import build_agents
from council.network import NetworkState, WhisperNetwork
from council.schemas import Action, Claim, Verdict, VerificationResult, stable_id
from council.tools import EvidenceTools
from council.verifier import Verifier
from optimization.decision_analysis import invalidation_test
from optimization.portfolio import MODE_CONDITIONAL, MODE_EVIDENCE, optimise, verify

EXECUTION_MODE = "RULE_BASED"


@dataclass
class CouncilResult:
    council_run_id: str
    config: str
    initial_claims: list[Claim]
    state: NetworkState
    verifications: dict[str, VerificationResult]
    impacts: list[dict[str, Any]]
    hearing: dict[str, Any]
    metrics: dict[str, Any]
    invalidation: list[dict[str, Any]] = field(default_factory=list)


def council_run_id(model: Any, config: str, version: str = "v1") -> str:
    """Deterministic: identical inputs and configuration replay to the same ID."""
    return stable_id("CR", model.fingerprint(), config, EXECUTION_MODE, version)


def run_council(repo: Any, model: Any, ledger_ids: set[str], gossip: bool,
                agent_ids: list[str] | None = None) -> CouncilResult:
    """Default (agent_ids=None) is the Step 4 six-agent council, unchanged. A subset runs the
    same verifier and optimiser with fewer specialists (used for Step 5 ablation)."""
    t0 = time.perf_counter()
    config = "B_WHISPER_NETWORK" if gossip else "A_NO_GOSSIP"
    if agent_ids is not None:
        config = "SINGLE_" + "+".join(sorted(agent_ids))
    rid = council_run_id(model, config)
    tools = EvidenceTools(repo, model)
    agents = [a.use(tools, rid) for a in build_agents()
              if agent_ids is None or a.agent_id in agent_ids]
    net = WhisperNetwork(agents, model, rid)
    st = net.state
    st.event(event_type="COUNCIL_STARTED", actor="ORCHESTRATOR",
             description=f"{config}: {len(agents)} specialists, mode {EXECUTION_MODE}")

    # 1) independent investigations (no agent sees another's output)
    initial: list[Claim] = []
    for a in agents:
        claims = a.investigate(model)
        assert len([c for c in claims if c.role == "primary"]) <= 1
        assert len([c for c in claims if c.role == "supporting"]) <= 1
        for c in claims:
            initial.append(c)
            st.event(event_type="INDEPENDENT_FINDING", actor=a.agent_id, claim_id=c.claim_id,
                     evidence_ref=",".join(c.evidence_ids + c.query_refs) or None,
                     verification_status="UNVERIFIED",
                     description=f"{a.name} ({c.role}, {c.action.value}): {c.statement[:250]}")
    # 2) Whisper Network (config B only)
    if gossip:
        net.run(initial)
    else:
        for c in initial:
            st.claims[c.claim_id] = c
    # 3) independent verification of every claim (initial + gossip-created)
    ver = Verifier(repo, model, ledger_ids)
    verifications: dict[str, VerificationResult] = {}
    for cid in sorted(st.claims, key=lambda k: (st.claims[k].round_number, k)):
        c = st.claims[cid]
        v = ver.verify(c, retracted=cid in st.retracted, claims=st.claims)
        verifications[cid] = v
        st.event(event_type="VERIFICATION_COMPLETED", actor="VERIFIER", claim_id=cid,
                 verification_status=v.verdict.value,
                 decision_consequence=f"{v.decision_relevance}; {v.parameter_admissibility}",
                 description=f"{c.agent_id} claim -> {v.verdict.value} "
                             f"(stat {v.statistical_support}, causal {v.causal_support})",
                 payload={"reasons": v.reasons})
    # 4) admissible changes -> existing Step 3 optimiser (versioned scenarios)
    base = {m: optimise(model, m) for m in (MODE_EVIDENCE, MODE_CONDITIONAL)}
    impacts: list[dict[str, Any]] = []
    for cid, v in sorted(verifications.items()):
        c = st.claims[cid]
        if c.proposed_change is None:
            continue
        st.event(event_type="ASSUMPTION_REVISION_PROPOSED", actor=c.agent_id, claim_id=cid,
                 description=f"{c.proposed_change.assumption_id} -> "
                             f"{c.proposed_change.value:,.2f} {c.proposed_change.unit}")
        if v.parameter_admissibility != "ADMISSIBLE_SCENARIO":
            st.event(event_type="CHANGE_REJECTED", actor="VERIFIER", claim_id=cid,
                     decision_consequence="baseline unchanged",
                     description="Proposed change not admissible; optimiser not run.")
            continue
        admission = ("VERIFIED_SCENARIO" if v.verdict == Verdict.VERIFIED
                     else "EXPLORATORY_SCENARIO")
        st.event(event_type="CHANGE_ADMITTED", actor="VERIFIER", claim_id=cid,
                 verification_status=admission,
                 description=f"Admitted as {admission} (baseline preserved).")
        p = c.proposed_change
        aset = stable_id("AS", rid, p.assumption_id, round(p.value, 6))
        m2 = model.with_assumption(p.assumption_id, p.value)
        for mode in (MODE_EVIDENCE, MODE_CONDITIONAL):
            after = optimise(m2, mode)
            changed = after.signature != base[mode].signature
            impacts.append({
                "council_run_id": rid, "claim_id": cid, "agent_id": c.agent_id,
                "assumption_set_id": aset, "assumption_id": p.assumption_id,
                "baseline_value": model.assumptions[p.assumption_id].value,
                "revised_value": p.value, "unit": p.unit, "mode": mode,
                "portfolio_before_id": base[mode].portfolio_id,
                "portfolio_before": base[mode].signature,
                "portfolio_after_id": after.portfolio_id, "portfolio_after": after.signature,
                "net_before": base[mode].net_benefit, "net_after": after.net_benefit,
                "net_difference": after.net_benefit - base[mode].net_benefit,
                "cost_after": after.total_cost, "portfolio_changed": changed,
                "verifier_verdict": v.verdict.value, "admission_class": admission,
                "constraint_check": "; ".join(verify(m2, after)) or "OK",
                "action_types_after": len({k.split("-")[1] for k in after.allocation})})
            st.event(event_type="OPTIMIZER_EXECUTED", actor="STEP3_OPTIMIZER", claim_id=cid,
                     portfolio_before=base[mode].portfolio_id,
                     portfolio_after=after.portfolio_id,
                     decision_consequence="PORTFOLIO_CHANGED" if changed else
                     "PORTFOLIO_RETAINED",
                     description=f"{mode}: {base[mode].signature} -> {after.signature} "
                                 f"({after.net_benefit - base[mode].net_benefit:+,.0f} USD)")
    # Explicit promotion-evidence invalidation through the Step 3 mechanism
    inval = [invalidation_test(model, "A08_promo_excess_theo_per_day", MODE_EVIDENCE),
             invalidation_test(model, "A08_promo_excess_theo_per_day", MODE_CONDITIONAL)]
    for i in inval:
        st.event(event_type="EVIDENCE_INVALIDATION_TEST", actor="STEP3_OPTIMIZER",
                 decision_consequence="PORTFOLIO_CHANGED" if i["decision_changed"]
                 else "PORTFOLIO_RETAINED",
                 description=f"{i['mode']}: invalidating promotion evidence: {i['before']} -> "
                             f"{i['after']} ({i['status']})")
    hearing = council_hearing(st, verifications)
    st.event(event_type="COUNCIL_CONCLUDED", actor="ORCHESTRATOR",
             decision_consequence="; ".join(hearing["conclusion"]),
             description="Council hearing recorded (no majority vote; verifier decides facts, "
                         "optimiser decides allocations).")
    metrics = council_metrics(initial, st, verifications, impacts,
                              time.perf_counter() - t0, gossip, tools)
    return CouncilResult(rid, config, initial, st, verifications, impacts, hearing, metrics,
                         inval)


def council_hearing(st: NetworkState, vers: dict[str, VerificationResult]) -> dict[str, Any]:
    by = {k: [cid for cid, v in vers.items() if v.verdict.value == k]
          for k in ("VERIFIED", "REJECTED", "INCONCLUSIVE", "BLOCKED")}
    contradictions = []
    claims = st.claims
    for a in claims.values():
        for b in claims.values():
            if a.claim_id < b.claim_id and a.target_assumption and \
                    a.target_assumption == b.target_assumption and a.agent_id != b.agent_id \
                    and {a.action, b.action} & {Action.SUPPORT} and \
                    {a.action, b.action} & {Action.CHALLENGE, Action.PROPOSE_SCENARIO}:
                contradictions.append({"claims": [a.claim_id, b.claim_id],
                                       "assumption": a.target_assumption,
                                       "resolution": "both kept: verifier verdicts "
                                       f"{vers[a.claim_id].verdict.value}/"
                                       f"{vers[b.claim_id].verdict.value}"})
    gossip_new = [c for c in claims.values() if c.role == "gossip"]
    material = [cid for cid, v in vers.items()
                if v.decision_relevance == "DECISION_RELEVANT" and
                v.verdict.value in ("VERIFIED", "INCONCLUSIVE") and cid not in st.retracted]
    conclusion = []
    if any(claims[c].target_assumption == "A08_promo_excess_theo_per_day" for c in material):
        conclusion.append("Promotion uplift evidence is decision-relevant and unresolved: "
                          "the evidence-supported portfolio is conditional on it")
    return {"verified": by["VERIFIED"], "rejected": by["REJECTED"],
            "inconclusive": by["INCONCLUSIVE"], "blocked": by["BLOCKED"],
            "retracted": sorted(st.retracted), "contradictions": contradictions,
            "new_from_gossip": [c.claim_id for c in gossip_new],
            "material_concerns": material,
            "admissible_revisions": [cid for cid, v in vers.items()
                                     if v.parameter_admissibility == "ADMISSIBLE_SCENARIO"],
            "evidence_requests": [c.claim_id for c in claims.values()
                                  if c.action == Action.REQUEST_EVIDENCE],
            "conclusion": conclusion or ["No decision-relevant change admitted"]}


def council_metrics(initial: list[Claim], st: NetworkState, vers: dict[str, VerificationResult],
                    impacts: list[dict[str, Any]], runtime: float, gossip: bool,
                    tools: EvidenceTools) -> dict[str, Any]:
    vals = list(vers.values())
    unsupported = [v for v in vals if v.verdict != Verdict.VERIFIED]
    init_q = {q for c in initial for q in c.query_refs}
    new_q = {q for c in st.claims.values() if c.role == "gossip" for q in c.query_refs} - init_q
    return {
        "claims_total": len(vals),
        "claims_verified": sum(v.verdict == Verdict.VERIFIED for v in vals),
        "claims_rejected": sum(v.verdict == Verdict.REJECTED for v in vals),
        "claims_inconclusive": sum(v.verdict == Verdict.INCONCLUSIVE for v in vals),
        "claims_blocked": sum(v.verdict == Verdict.BLOCKED for v in vals),
        "unsupported_claim_rate": len(unsupported) / len(vals) if vals else 0.0,
        "unresolved_hypotheses": sum(1 for c in st.claims.values()
                                     if c.classification == "HYPOTHESIS"
                                     and c.claim_id not in st.retracted),
        "verified_decision_relevant_objections": sum(
            1 for cid, v in vers.items() if v.verdict == Verdict.VERIFIED
            and v.decision_relevance == "DECISION_RELEVANT"
            and st.claims[cid].action != Action.SUPPORT),
        # Same-origin follow-ups (e.g. a CFO consequence of a Statistician challenge) are
        # not independent objections: deduplicate by origin claim.
        "independent_decision_relevant_objections": len({
            st.claims[cid].origin_claim_id or cid for cid, v in vers.items()
            if v.verdict == Verdict.VERIFIED and v.decision_relevance == "DECISION_RELEVANT"
            and st.claims[cid].action != Action.SUPPORT}),
        "retractions": len(st.retracted),
        "messages_delivered": sum(m.message_status == "DELIVERED" for m in st.messages),
        "messages_suppressed_duplicate": sum(m.message_status == "SUPPRESSED_DUPLICATE"
                                             for m in st.messages),
        "messages_blocked": sum(m.message_status in ("BLOCKED_CYCLE", "BUDGET_EXCEEDED",
                                                     "QUARANTINED") for m in st.messages),
        "messages_flagged_retracted_origin": len(st.flagged),
        "new_evidence_queries_from_gossip": len(new_q),
        "admissible_changes": len({i["claim_id"] for i in impacts}),
        "decision_changing_admissible_challenges": len({i["claim_id"] for i in impacts
                                                        if i["portfolio_changed"]}),
        "decision_changing_verified_challenges": len({
            i["claim_id"] for i in impacts if i["portfolio_changed"]
            and i["admission_class"] == "VERIFIED_SCENARIO"}),
        "portfolio_changes": sum(i["portfolio_changed"] for i in impacts),
        "runtime_seconds": round(runtime, 3), "tool_calls": len(tools.calls),
        "llm_tokens": 0, "llm_cost_usd": 0.0, "execution_mode": EXECUTION_MODE,
        "gossip_enabled": gossip,
    }
