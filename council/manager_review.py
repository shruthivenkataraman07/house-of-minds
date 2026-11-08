"""Council review of the manager's proposal to replace the 10 lowest-earning machines.

Existing agents review the proposal with machine-level tools; the existing deterministic
verifier reproduces every number. Each machine is resolved from VERIFIED claims only, with
the same ordered rules as the analytic verdict (analytics.replacement). No majority vote.
"""

from __future__ import annotations

from typing import Any

from council.agents import build_agents
from council.schemas import Claim, Verdict, stable_id
from council.tools import EvidenceTools
from council.verifier import Verifier

REVIEWERS = ("AG1_STATISTICIAN", "AG2_DEMAND", "AG3_OPERATIONS", "AG6_CFO")


def run_manager_review(repo: Any, model: Any, ledger_ids: set[str], machine_ids: list[str]
                       ) -> dict[str, Any]:
    rid = stable_id("CR", model.fingerprint(), "MANAGER_REVIEW", ",".join(machine_ids))
    tools = EvidenceTools(repo, model)
    claims: list[Claim] = []
    for a in build_agents():
        if a.agent_id in REVIEWERS:
            claims += a.use(tools, rid).review_proposal(machine_ids)
    ver = Verifier(repo, model, ledger_ids)
    vers = {c.claim_id: ver.verify(c) for c in claims}
    resolutions = []
    for mid in machine_ids:
        mine = {c.claim_id.split("|")[0]: c for c in claims
                if c.financial_relevance == f"replacement of {mid}"}
        by_kind: dict[str, Claim] = {}
        for c in claims:
            if c.financial_relevance == f"replacement of {mid}":
                by_kind[c.role.removeprefix("review:")] = c

        def ok(kind: str, by_kind: dict[str, Claim] = by_kind) -> Claim | None:
            c = by_kind.get(kind)
            return c if c is not None and vers[c.claim_id].verdict == Verdict.VERIFIED else None

        exp, hit, econ = ok("exposure"), ok("hit_rate"), ok("economics")
        reasons = []
        if exp is not None and "retired" in exp.statement:
            v = "RETIRED_ALREADY"
            reasons.append(exp.claim_id)
        elif hit is not None and (hit.numeric_result or 0) > 4.656:
            v = "DO_NOT_REPLACE_INSPECT"
            reasons.append(hit.claim_id)
        elif econ is not None and (econ.numeric_result or 0) <= 0:
            v = "DO_NOT_REPLACE_NOT_ECONOMIC"
            reasons.append(econ.claim_id)
        elif econ is not None:
            v = "INSUFFICIENT_EVIDENCE"
            reasons.append(econ.claim_id)
        else:
            v = "INSUFFICIENT_EVIDENCE"
        unverified = [k for k, c in by_kind.items()
                      if vers[c.claim_id].verdict != Verdict.VERIFIED]
        resolutions.append({"council_run_id": rid, "machine_id": mid,
                            "manager_decision": "REPLACE",
                            "council_verdict": v, "deciding_claims": ",".join(reasons),
                            "claims_reviewed": len(mine), "unverified_claim_kinds":
                            ",".join(unverified) or "none",
                            "supporting_kinds": ",".join(sorted(by_kind))})
    return {"council_run_id": rid, "claims": claims, "verifications": vers,
            "resolutions": resolutions, "tool_calls": len(tools.calls)}
