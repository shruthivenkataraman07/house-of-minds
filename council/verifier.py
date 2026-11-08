"""Deterministic evidence verifier, independent of the agents.

A claim is never accepted because agents agree, because of seniority or wording, or because
it was repeated. Each claim is checked on six separate dimensions by re-running its tool
calls on a fresh tool instance and by consulting the canonical Step 3 model:

  SOURCE_VALID            evidence IDs exist in evidence_ledger; tools are allowlisted;
                          assumption/investment references exist
  ARITHMETIC_VALID        stated numeric result reproduces exactly from its tool calls
  STATISTICAL_SUPPORT     enough observations for what is claimed
  CAUSAL_SUPPORT          causal claims need a design that identifies causes (none here)
  DECISION_RELEVANCE      would the argued side of the assumption change a baseline portfolio
  PARAMETER_ADMISSIBILITY proposed value: matching units, inside the evidence range,
                          derived from a reproduced tool result
"""

from __future__ import annotations

import math
from typing import Any

from council.schemas import Action, Claim, Verdict, VerificationResult
from council.tools import ALLOWLIST, EvidenceTools, ToolError
from optimization.portfolio import MODE_CONDITIONAL, MODE_EVIDENCE, optimise

MIN_SAMPLE_FOR_ESTIMATE = 5


class Verifier:
    def __init__(self, repo: Any, model: Any, ledger_ids: set[str]) -> None:
        self.repo, self.model, self.ledger_ids = repo, model, ledger_ids
        self.tools = EvidenceTools(repo, model)  # fresh instance, not the agents'
        self._base = {m: optimise(model, m).signature for m in (MODE_EVIDENCE,
                                                                 MODE_CONDITIONAL)}
        self.investments = {c.candidate_id for c in model.candidates} | {
            "PORTFOLIO", "COMP", "MANAGER_PROPOSAL"}

    def _reproduce(self, claim: Claim) -> tuple[bool | None, float | None, list[str]]:
        reasons: list[str] = []
        if claim.numeric_result is None:
            return None, None, reasons
        if not claim.tool_calls:
            reasons.append("numeric value has no tool provenance (invented figure)")
            return False, None, reasons
        reproduced = None
        for tool, params in claim.tool_calls:
            try:
                r = self.tools.call(tool, **dict(params))
            except (ToolError, TypeError) as e:
                reasons.append(f"tool call failed: {e}")
                return False, None, reasons
            if math.isclose(r.value, claim.numeric_result, rel_tol=1e-9, abs_tol=1e-9):
                reproduced = r.value
        if reproduced is None:
            reasons.append("numeric result does not match any of its tool results")
            return False, None, reasons
        return True, reproduced, reasons

    def _changes_portfolio(self, assumption_id: str, value: float) -> bool:
        m = self.model.with_assumption(assumption_id, value)
        return any(optimise(m, mode).signature != self._base[mode]
                   for mode in (MODE_EVIDENCE, MODE_CONDITIONAL))

    def verify(self, claim: Claim, retracted: bool = False,
               claims: dict[str, Claim] | None = None) -> VerificationResult:
        reasons: list[str] = []
        # SOURCE
        src = True
        missing = [e for e in claim.evidence_ids if e not in self.ledger_ids]
        if missing:
            src = False
            reasons.append(f"evidence IDs not in evidence_ledger: {missing}")
        bad_tools = [t for t, _ in claim.tool_calls if t not in ALLOWLIST]
        if bad_tools:
            src = False
            reasons.append(f"non-allowlisted tools: {bad_tools}")
        if claim.target_assumption and claim.target_assumption not in self.model.assumptions:
            src = False
            reasons.append(f"unknown assumption {claim.target_assumption}")
        if claim.target_investment not in self.investments:
            src = False
            reasons.append(f"unknown investment {claim.target_investment}")
        # ARITHMETIC
        arith, reproduced, r2 = self._reproduce(claim)
        reasons += r2
        # STATISTICAL
        if claim.classification == "HYPOTHESIS":
            stat = "UNSUPPORTED"
        elif claim.action in (Action.FLAG_UNCERTAINTY, Action.CHALLENGE) and \
                claim.proposed_change is None:
            stat = "SUPPORTED" if arith is not False else "UNSUPPORTED"  # limits, not estimates
        elif claim.proposed_change is not None and \
                claim.proposed_change.basis.endswith((".low", ".high")):
            stat = "SUPPORTED"  # an observed empirical bound, not a new estimate
        elif claim.proposed_change is not None or claim.action == Action.SUPPORT:
            n = claim.sample_size or 0
            stat = "SUPPORTED" if n >= MIN_SAMPLE_FOR_ESTIMATE else "WEAK"
        else:
            stat = "NOT_APPLICABLE"
        # CAUSAL: no experiment or identification strategy exists in this dataset
        causal = "UNSUPPORTED" if claim.causal_claim else "NOT_CLAIMED"
        # DECISION RELEVANCE
        rel = "UNKNOWN"
        a = self.model.assumptions.get(claim.target_assumption or "")
        if claim.proposed_change is not None and a is not None:
            rel = ("DECISION_RELEVANT" if self._changes_portfolio(
                a.assumption_id, claim.proposed_change.value) else "NOT_DECISION_RELEVANT")
        elif a is not None and claim.argued_direction:
            sides = {"low": [a.low], "high": [a.high], "both": [a.low, a.high]}[
                claim.argued_direction]
            rel = ("DECISION_RELEVANT" if any(self._changes_portfolio(a.assumption_id, v)
                                              for v in sides) else "NOT_DECISION_RELEVANT")
        elif claims and any(claims.get(d) is not None and claims[d].proposed_change is not None
                            for d in claim.depends_on):
            # a follow-up on another claim's change: relevant only if that change moves a
            # baseline portfolio (re-computed here, not taken from the claim's wording)
            dep = next(claims[d] for d in claim.depends_on
                       if claims.get(d) is not None and claims[d].proposed_change is not None)
            p = dep.proposed_change
            assert p is not None
            rel = ("DECISION_RELEVANT" if self._changes_portfolio(p.assumption_id, p.value)
                   else "NOT_DECISION_RELEVANT")
        elif claim.target_investment == "PORTFOLIO":
            rel = "DECISION_RELEVANT"
        # PARAMETER ADMISSIBILITY (scenario only; baselines are never edited)
        adm = "NO_CHANGE_PROPOSED"
        if claim.proposed_change is not None:
            p = claim.proposed_change
            ok = (a is not None and p.assumption_id == a.assumption_id and p.unit == a.unit
                  and a.low - 1e-9 <= p.value <= a.high + 1e-9 and arith is True
                  and src and p.basis.startswith("tool:") and not retracted)
            adm = "ADMISSIBLE_SCENARIO" if ok else "NOT_ADMISSIBLE"
            if not ok:
                reasons.append("proposed change not admissible (unit/range/provenance)")
        # VERDICT
        if not src:
            verdict = Verdict.BLOCKED if bad_tools else Verdict.REJECTED
        elif arith is False:
            verdict = Verdict.REJECTED
        elif retracted:
            verdict = Verdict.INCONCLUSIVE
            reasons.append("retracted by its author")
        elif stat in ("UNSUPPORTED", "WEAK") or causal == "UNSUPPORTED":
            verdict = Verdict.INCONCLUSIVE
        else:
            verdict = Verdict.VERIFIED
        return VerificationResult(
            claim_id=claim.claim_id, council_run_id=claim.council_run_id, source_valid=src,
            arithmetic_valid=arith, statistical_support=stat, causal_support=causal,
            decision_relevance=rel, parameter_admissibility=adm, verdict=verdict,
            reasons=reasons, independent_sources=len(set(claim.query_refs)),
            reproduced_value=reproduced)
