"""Typed council records. Every agent output is validated against these schemas."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def stable_id(prefix: str, *parts: object) -> str:
    return prefix + "-" + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[
        :10].upper()


class Action(StrEnum):
    SUPPORT = "SUPPORT"
    CHALLENGE = "CHALLENGE"
    REQUEST_EVIDENCE = "REQUEST_EVIDENCE"
    FLAG_UNCERTAINTY = "FLAG_UNCERTAINTY"
    PROPOSE_SCENARIO = "PROPOSE_SCENARIO"
    INVALIDATE_UNSUPPORTED_ASSUMPTION = "INVALIDATE_UNSUPPORTED_ASSUMPTION"
    ABSTAIN = "ABSTAIN"


class MsgType(StrEnum):
    WHISPER = "WHISPER"
    REQUEST_CHECK = "REQUEST_CHECK"
    COUNTERCLAIM = "COUNTERCLAIM"
    ESCALATE = "ESCALATE"
    RETRACT = "RETRACT"
    ACKNOWLEDGE = "ACKNOWLEDGE"


class Verdict(StrEnum):
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED"


class ProposedChange(BaseModel):
    model_config = ConfigDict(frozen=True)
    assumption_id: str
    value: float
    unit: str
    basis: str  # e.g. "tool:promo_event_excess.low"


class Claim(BaseModel):
    """One agent claim. Immutable once created (frozen)."""
    model_config = ConfigDict(frozen=True)
    claim_id: str
    council_run_id: str
    agent_id: str
    role: str  # primary | supporting | gossip
    target_investment: str
    target_assumption: str | None
    statement: str = Field(max_length=600)
    action: Action
    evidence_ids: tuple[str, ...] = ()
    query_refs: tuple[str, ...] = ()  # tool query references (reproducible)
    tool_calls: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()
    numeric_result: float | None = None
    numeric_unit: str | None = None
    alternative_explanation: str = ""
    limitation: str = ""
    classification: str  # VERIFIED_FACT_CANDIDATE | HYPOTHESIS | OBSERVATIONAL
    causal_claim: bool = False
    financial_relevance: str = ""
    proposed_change: ProposedChange | None = None
    sample_size: int | None = None  # observations behind the numeric result
    argued_direction: str | None = None  # low | high | both: side of the range argued
    origin_claim_id: str | None = None  # set when built on another agent's claim
    depends_on: tuple[str, ...] = ()
    round_number: int = 0

    @field_validator("classification")
    @classmethod
    def _cls(cls, v: str) -> str:
        if v not in {"VERIFIED_FACT_CANDIDATE", "HYPOTHESIS", "OBSERVATIONAL"}:
            raise ValueError(f"bad classification {v}")
        return v


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)
    message_id: str
    council_run_id: str
    sender_agent_id: str
    recipient_agent_id: str
    message_type: MsgType
    claim_id: str
    parent_message_id: str | None
    origin_claim_id: str
    origin_agent_id: str
    forward_chain: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    statement: str = Field(max_length=600)
    verification_request: str = ""
    uncertainty_status: str  # UNVERIFIED | VERIFIED | REJECTED | INCONCLUSIVE | RETRACTED
    round_number: int
    sequence: int
    message_status: str = "DELIVERED"  # DELIVERED | SUPPRESSED_DUPLICATE | BLOCKED_CYCLE
                                       # | BUDGET_EXCEEDED | FLAGGED_RETRACTED_ORIGIN
                                       # | QUARANTINED


class VerificationResult(BaseModel):
    claim_id: str
    council_run_id: str
    source_valid: bool
    arithmetic_valid: bool | None
    statistical_support: str  # SUPPORTED | WEAK | NOT_APPLICABLE | UNSUPPORTED
    causal_support: str  # SUPPORTED | NOT_CLAIMED | UNSUPPORTED
    decision_relevance: str  # DECISION_RELEVANT | NOT_DECISION_RELEVANT | UNKNOWN
    parameter_admissibility: str  # ADMISSIBLE_SCENARIO | NOT_ADMISSIBLE | NO_CHANGE_PROPOSED
    verdict: Verdict
    reasons: list[str]
    independent_sources: int
    reproduced_value: float | None = None


class Event(BaseModel):
    council_run_id: str
    sequence: int
    event_type: str
    actor: str
    source: str | None = None
    target: str | None = None
    claim_id: str | None = None
    message_id: str | None = None
    evidence_ref: str | None = None
    verification_status: str | None = None
    decision_consequence: str | None = None
    portfolio_before: str | None = None
    portfolio_after: str | None = None
    description: str = Field(max_length=400)
    payload: dict[str, Any] = Field(default_factory=dict)
