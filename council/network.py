"""The Whisper Network: selective, bounded, provenance-preserving agent messaging.

Routing is deterministic: score = 3*expertise + 2*unresolved + 2*decision consequence
+ 1*novelty - 2*redundancy, recipients with score >= MIN_SCORE, top 2 per claim.
Limits: 2 rounds, 2 outgoing messages per agent per round (24 max). Forwarded messages keep
the origin claim and forward chain; repeats are suppressed; cycles are blocked; retractions
flag every downstream message (nothing is deleted). Message text is data, never executed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from council.agents import Agent, Reply
from council.schemas import Action, Claim, Event, Message, MsgType, stable_id

MAX_ROUNDS = 2
MAX_OUT_PER_ROUND = 2
MIN_SCORE = 5
INJECTION = re.compile(r"(ignore (all|previous|prior) instructions|system prompt|"
                       r"you are now|set .* to \d|drop table|delete from|approve the "
                       r"portfolio|override)", re.I)
WHISPER_ACTIONS = {Action.CHALLENGE, Action.FLAG_UNCERTAINTY, Action.PROPOSE_SCENARIO,
                   Action.REQUEST_EVIDENCE, Action.INVALIDATE_UNSUPPORTED_ASSUMPTION}


def looks_like_injection(text: str) -> bool:
    return bool(INJECTION.search(text or ""))


@dataclass
class NetworkState:
    run_id: str
    messages: list[Message] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    claims: dict[str, Claim] = field(default_factory=dict)
    retracted: set[str] = field(default_factory=set)
    flagged: dict[str, str] = field(default_factory=dict)  # message_id -> reason
    sent: dict[tuple[str, int], int] = field(default_factory=dict)
    seen: set[tuple[str, str, str]] = field(default_factory=set)  # (recipient, origin, type)
    seq: int = 0

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def event(self, **kw: Any) -> None:
        self.events.append(Event(council_run_id=self.run_id, sequence=self.next_seq(), **kw))


def route_score(agent: Agent, claim: Claim, sender: Agent, received_origins: set[str],
                primary_targets: dict[str, str | None]) -> int:
    if agent.agent_id == sender.agent_id:
        return -99
    topic = claim.target_assumption or "portfolio"
    expertise = 1 if (topic in agent.expertise or
                      (claim.target_investment == "COMP" and "comp" in agent.expertise)
                      or "financial_consequence" in agent.expertise) else 0
    if claim.classification == "HYPOTHESIS" and "timing" in agent.expertise:
        expertise = 1  # hypotheses about causes need a timing / confounding check
    unresolved = 1 if (claim.classification != "VERIFIED_FACT_CANDIDATE"
                       or claim.proposed_change is not None) else 0
    consequence = 1 if (claim.proposed_change is not None
                        or claim.target_investment in {"INV-PROMO", "PORTFOLIO"}) else 0
    novelty = 0 if claim.claim_id in received_origins else 1
    redundancy = 1 if (primary_targets.get(agent.agent_id) == claim.target_assumption
                       and claim.classification != "HYPOTHESIS"
                       and "financial_consequence" not in agent.expertise) else 0
    return 3 * expertise + 2 * unresolved + 2 * consequence + novelty - 2 * redundancy


class WhisperNetwork:
    def __init__(self, agents: list[Agent], model: Any, run_id: str,
                 max_rounds: int = MAX_ROUNDS) -> None:
        self.max_rounds = min(max_rounds, MAX_ROUNDS)
        self.agents = {a.agent_id: a for a in agents}
        self.model = model
        self.state = NetworkState(run_id)

    # ---------------------------------------------------------------- sending
    def send(self, sender: str, recipient: str, mtype: MsgType, claim: Claim, statement: str,
             rnd: int, parent: Message | None = None, verification_request: str = "") -> Message:
        st = self.state
        origin = claim.origin_claim_id or claim.claim_id
        origin_agent = st.claims[origin].agent_id if origin in st.claims else claim.agent_id
        base_chain = parent.forward_chain if parent else (origin_agent,)
        chain = base_chain + ((sender,) if base_chain[-1] != sender else ())
        status = "DELIVERED"
        forwardable = mtype in (MsgType.WHISPER, MsgType.REQUEST_CHECK)
        if looks_like_injection(statement) or looks_like_injection(claim.statement):
            status = "QUARANTINED"
        elif forwardable and any((recipient, origin, t) in st.seen
                                 for t in (MsgType.WHISPER.value, MsgType.REQUEST_CHECK.value)):
            status = "SUPPRESSED_DUPLICATE"  # recipient already has this origin claim
        elif forwardable and recipient in chain:
            status = "BLOCKED_CYCLE"
        elif rnd > self.max_rounds or (st.sent.get((sender, rnd), 0) >= MAX_OUT_PER_ROUND
                                  and mtype != MsgType.RETRACT):
            status = "BUDGET_EXCEEDED"
        uncertainty = "RETRACTED" if origin in st.retracted else (
            "UNVERIFIED" if claim.classification != "VERIFIED_FACT_CANDIDATE" else
            "UNVERIFIED_FACT_CANDIDATE")
        msg = Message(
            message_id=stable_id("MSG", st.run_id, sender, recipient, mtype, claim.claim_id,
                                 rnd, parent.message_id if parent else ""),
            council_run_id=st.run_id, sender_agent_id=sender, recipient_agent_id=recipient,
            message_type=mtype, claim_id=claim.claim_id,
            parent_message_id=parent.message_id if parent else None, origin_claim_id=origin,
            origin_agent_id=origin_agent, forward_chain=chain,
            evidence_ids=claim.evidence_ids, statement=statement[:600],
            verification_request=verification_request, uncertainty_status=uncertainty,
            round_number=rnd, sequence=st.next_seq(), message_status=status)
        st.messages.append(msg)
        if status == "DELIVERED":
            st.sent[(sender, rnd)] = st.sent.get((sender, rnd), 0) + 1
            st.seen.add((recipient, origin, mtype.value))
        st.event(event_type=f"MESSAGE_{mtype.value}" if status == "DELIVERED"
                 else f"MESSAGE_{status}", actor=sender, source=sender, target=recipient,
                 claim_id=claim.claim_id, message_id=msg.message_id,
                 evidence_ref=",".join(claim.evidence_ids) or None,
                 verification_status=uncertainty,
                 description=f"{mtype.value} {sender} -> {recipient} on {origin} "
                             f"({status.lower()})")
        return msg

    # ---------------------------------------------------------------- rounds
    def run(self, initial: list[Claim]) -> NetworkState:
        st = self.state
        for c in initial:
            st.claims[c.claim_id] = c
        primary = {a: next((c.target_assumption for c in initial
                            if c.agent_id == a and c.role == "primary"), None)
                   for a in self.agents}
        received: dict[str, set[str]] = {a: set() for a in self.agents}
        inbox: list[Message] = []
        # Round 1: each agent whispers its unresolved / decision-relevant claims
        for sender_id in sorted(self.agents):
            sender = self.agents[sender_id]
            for c in [c for c in initial if c.agent_id == sender_id
                      and c.action in WHISPER_ACTIONS]:
                ranked = sorted(((route_score(a, c, sender, received[a.agent_id], primary),
                                  a.agent_id) for a in self.agents.values()),
                                key=lambda x: (-x[0], x[1]))
                for score, rid in ranked[:2]:
                    if score < MIN_SCORE:
                        continue
                    mtype = (MsgType.REQUEST_CHECK if c.classification == "HYPOTHESIS"
                             else MsgType.WHISPER)
                    m = self.send(sender_id, rid, mtype, c, c.statement, 1,
                                  verification_request="Check with your own evidence "
                                                       f"(routing score {score}).")
                    if m.message_status == "DELIVERED":
                        received[rid].add(c.claim_id)
                        inbox.append(m)
        # Rounds 1-2: recipients respond in sequence; replies happen in round 2
        rnd = 1
        while inbox and rnd <= self.max_rounds:
            nxt: list[Message] = []
            for m in sorted(inbox, key=lambda x: x.sequence):
                agent = self.agents.get(m.recipient_agent_id)
                if agent is None:
                    continue
                terminal = m.message_type in (MsgType.ACKNOWLEDGE, MsgType.ESCALATE)
                st.event(event_type="MESSAGE_RECEIVED", actor=agent.agent_id,
                         source=m.sender_agent_id, target=agent.agent_id,
                         claim_id=m.claim_id, message_id=m.message_id,
                         description=f"{agent.name} received {m.message_type.value}")
                replies = [] if terminal else agent.respond(m, st.claims, self.model)
                for rep in replies:
                    out = self._deliver(agent, m, rep, rnd + 1 if rnd == 1 else rnd)
                    if out is not None and out.message_status == "DELIVERED" and \
                            out.recipient_agent_id in self.agents:
                        nxt.append(out)
            inbox = nxt
            rnd += 1
        return st

    def _deliver(self, agent: Agent, parent: Message, rep: Reply, rnd: int) -> Message | None:
        st = self.state
        if rep.claim is not None:
            st.claims[rep.claim.claim_id] = rep.claim
            st.event(event_type="GOSSIP_FINDING", actor=agent.agent_id,
                     claim_id=rep.claim.claim_id,
                     evidence_ref=",".join(rep.claim.query_refs) or None,
                     description=f"{agent.name} produced new evidence: "
                                 f"{rep.claim.statement[:200]}")
        about = rep.claim or st.claims.get(rep.about_claim_id or parent.claim_id)
        if about is None:
            return None
        if rep.msg_type == MsgType.RETRACT and rep.retract_claim_id:
            self.retract(rep.retract_claim_id, agent.agent_id)
        if rep.recipient == "VERIFIER":
            st.event(event_type="ESCALATION", actor=agent.agent_id, source=agent.agent_id,
                     target="VERIFIER", claim_id=about.claim_id,
                     decision_consequence="portfolio may change",
                     description=rep.statement[:400])
            return self.send(agent.agent_id, "VERIFIER", rep.msg_type, about, rep.statement,
                             min(rnd, MAX_ROUNDS), parent)
        return self.send(agent.agent_id, rep.recipient, rep.msg_type, about, rep.statement,
                         rnd, parent)

    def retract(self, claim_id: str, by: str) -> None:
        """Mark a claim retracted and flag every message that depends on it."""
        st = self.state
        st.retracted.add(claim_id)
        dependents = {claim_id} | {c.claim_id for c in st.claims.values()
                                   if claim_id in c.depends_on}
        for m in st.messages:
            if m.origin_claim_id in dependents or m.claim_id in dependents:
                st.flagged[m.message_id] = f"origin {claim_id} retracted by {by}"
        st.event(event_type="CLAIM_RETRACTED", actor=by, claim_id=claim_id,
                 verification_status="RETRACTED",
                 description=f"{by} retracted {claim_id}; "
                             f"{sum(1 for v in st.flagged.values() if claim_id in v)} "
                             "downstream messages flagged")
