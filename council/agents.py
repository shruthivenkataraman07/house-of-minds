"""Six rule-based specialist agents (execution mode RULE_BASED).

Each agent has a distinct mandate, falsifiable hypothesis, tool allowlist and expertise
tags. Investigations are deterministic analyses of verified data through council.tools.
Agents emit typed Claims (max 1 primary + 1 supporting) and respond to messages; they
cannot change portfolios: only the verifier + Step 3 optimiser can.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from council.schemas import Action, Claim, Message, MsgType, ProposedChange, stable_id
from council.tools import EvidenceTools, ToolResult


@dataclass
class Reply:
    msg_type: MsgType
    recipient: str
    statement: str
    claim: Claim | None = None  # new claim created while responding (gossip finding)
    about_claim_id: str | None = None  # claim the message is about (else the new claim)
    retract_claim_id: str | None = None


@dataclass
class Agent:
    agent_id: str
    name: str
    mandate: str
    hypothesis: str
    tools: tuple[str, ...]
    expertise: tuple[str, ...]  # assumption ids / topics used by routing
    escalation_condition: str
    run_id: str = ""
    _tools: EvidenceTools | None = field(default=None, repr=False)

    # --------------------------------------------------------------- helpers
    def use(self, tools: EvidenceTools, run_id: str) -> Agent:
        self._tools, self.run_id = tools, run_id
        return self

    def t(self, name: str, **kw: str) -> ToolResult:
        if name not in self.tools:
            raise PermissionError(f"{self.agent_id} may not call {name}")
        assert self._tools is not None
        return self._tools.call(name, **kw)

    def claim(self, role: str, n: int, results: list[ToolResult], **kw: Any) -> Claim:
        return Claim(
            claim_id=stable_id("CLM", self.run_id, self.agent_id, role, n),
            council_run_id=self.run_id, agent_id=self.agent_id, role=role,
            evidence_ids=tuple(sorted({e for r in results for e in r.evidence_ids})),
            query_refs=tuple(r.query_ref for r in results),
            tool_calls=tuple((r.tool, r.params) for r in results), **kw)

    def investigate(self, model: Any) -> list[Claim]:
        raise NotImplementedError

    def respond(self, msg: Message, claims: dict[str, Claim], model: Any) -> list[Reply]:
        """Default: stay silent when the mandate adds no new evidence (saves budget)."""
        return []

    def review_proposal(self, machine_ids: list[str]) -> list[Claim]:
        """Machine-level review of the manager's replacement proposal (default: none)."""
        return []

    def _review_claim(self, mid: str, kind: str, r: ToolResult, statement: str,
                      action: Action, **kw: Any) -> Claim:
        return self.claim(f"review:{kind}", int(mid[2:]), [r],
                          target_investment="MANAGER_PROPOSAL", target_assumption=None,
                          statement=statement[:600], action=action, numeric_result=r.value,
                          numeric_unit=r.unit, classification="VERIFIED_FACT_CANDIDATE",
                          financial_relevance=f"replacement of {mid}", **kw)


def promo_breakeven(model: Any) -> float:
    """Excess theo/day at which one promotion weekend breaks even (Step 3 economics)."""
    from optimization.investment_model import unit_cost_usd
    return unit_cost_usd(model, "A-PROMO") / (3 * model.facts["floor_contribution_factor"])


class Statistician(Agent):
    def investigate(self, model: Any) -> list[Claim]:
        ex, sd = self.t("promo_event_excess"), self.t("weekend_noise_sd")
        low, n = ex.detail["low"], ex.detail["events"]
        be = promo_breakeven(model)
        z = low / sd.value
        primary = self.claim(
            "primary", 1, [ex, sd], target_investment="INV-PROMO",
            target_assumption="A08_promo_excess_theo_per_day",
            statement=(f"Promotion uplift rests on {n} events with no control group. The weaker "
                       f"event's excess (${low:,.0f}/day) is {z:.2f} SD of ordinary Fri-Sun "
                       f"variation (SD ${sd.value:,.0f}/day) and below the ${be:,.0f}/day "
                       "break-even, so the evidence cannot separate a profitable promotion from "
                       "noise."),
            action=Action.PROPOSE_SCENARIO, numeric_result=low, numeric_unit="USD/day",
            alternative_explanation="Event-day highs may reflect seasonal or event-calendar "
                                    "demand rather than the promotion.",
            limitation="Two observations; noise SD from 60 non-event weekend days.",
            classification="OBSERVATIONAL", sample_size=n, argued_direction="low",
            financial_relevance="Decides whether $30,000 of promotions is funded.",
            proposed_change=ProposedChange(
                assumption_id="A08_promo_excess_theo_per_day", value=low, unit="USD/day",
                basis="tool:promo_event_excess.low"))
        support = self.claim(
            "supporting", 2, [sd], target_investment="INV-PROMO",
            target_assumption="A08_promo_excess_theo_per_day",
            statement=(f"Ordinary weekend theo varies by SD ${sd.value:,.0f}/day "
                       f"({sd.detail['n_days']} non-event Fri-Sun days), a large share of the "
                       "estimated promotion effect."),
            action=Action.FLAG_UNCERTAINTY, numeric_result=sd.value, numeric_unit="USD/day",
            classification="VERIFIED_FACT_CANDIDATE", sample_size=sd.detail["n_days"],
            financial_relevance="Width of plausible promotion outcomes.")
        return [primary, support]

    def respond(self, msg: Message, claims: dict[str, Claim], model: Any) -> list[Reply]:
        c = claims.get(msg.origin_claim_id)
        if c and c.target_investment == "COMP" and c.classification == "HYPOTHESIS":
            r = self.t("comp_change_date")
            stmt = (f"Comp points price changed on {r.detail['change_date']}; the next "
                    f"property promotion started {r.detail['next_property_promo_start']}. "
                    "The comp cost increase predates the promotion, so promotions cannot "
                    "have caused it.")
            counter = self.claim("gossip", 10, [r], target_investment="COMP",
                                 target_assumption="A07_comp_cost_saving_rate",
                                 statement=stmt, action=Action.CHALLENGE,
                                 numeric_result=r.value, numeric_unit=r.unit,
                                 classification="VERIFIED_FACT_CANDIDATE",
                                 origin_claim_id=c.claim_id, depends_on=(c.claim_id,),
                                 round_number=msg.round_number + 1,
                                 financial_relevance="Removes a suspected promotion cost.")
            out = [Reply(MsgType.COUNTERCLAIM, c.agent_id, stmt, counter)]
            if msg.sender_agent_id != c.agent_id:  # also correct the forwarder
                out.append(Reply(MsgType.COUNTERCLAIM, msg.sender_agent_id, stmt, counter))
            return out
        return super().respond(msg, claims, model)


def _stat_review(self: Agent, machine_ids: list[str]) -> list[Claim]:
    out = []
    for mid in machine_ids:
        r = self.t("machine_luck", machine_id=mid)
        sig = abs(r.value) >= 3.773  # Step 1 rule: Bonferroni p < 0.05 over 310 machines
        out.append(self._review_claim(
            mid, "luck", r,
            f"{mid}: house win minus theo is ${r.detail['residual_usd']:,.0f} "
            f"(luck z {r.value:.2f}); " + ("beyond chance: luck does not explain it."
                                          if sig else "within chance: weak results may be "
                                          "payout luck, not a weak machine."),
            Action.CHALLENGE if not sig else Action.FLAG_UNCERTAINTY,
            alternative_explanation="payout variance", sample_size=181))
    return out


Statistician.review_proposal = _stat_review  # type: ignore[method-assign]


class DemandStrategist(Agent):
    def investigate(self, model: Any) -> list[Claim]:
        pit, b40 = self.t("zone_occupancy", zone_id="Z-PIT"), self.t(
            "zone_occupancy", zone_id="Z-B40")
        el = self.t("zone_count_elasticity", zone_id="Z-PIT")
        if not el.detail.get("identifiable", False):
            return [self.claim("primary", 1, [el], target_investment="INV-MOVE-M-1154-Z-PIT",
                               target_assumption="A09_move_location_transfer",
                               statement="Abstain: Center Pit machine counts never varied, so "
                                         "demand transfer cannot be assessed.",
                               action=Action.ABSTAIN, classification="OBSERVATIONAL")]
        primary = self.claim(
            "primary", 1, [pit, b40, el], target_investment="INV-MOVE-M-1154-Z-PIT",
            target_assumption="A09_move_location_transfer",
            statement=(f"Center Pit is {pit.value:.1%} occupied (Back Forty {b40.value:.1%}), so "
                       "moved machines are not capacity-blocked. Historically each extra "
                       f"Center Pit machine added {el.value:.2f}x the mean machine's theo, but "
                       f"from only {el.detail['distinct_counts']} distinct machine counts: demand "
                       "transfer (decision flips at 20-21%) is not identified."),
            action=Action.FLAG_UNCERTAINTY, numeric_result=el.value, numeric_unit="ratio",
            alternative_explanation="Machine-count changes coincided with other changes "
                                    "(installs, seasonality).",
            limitation="Observational; 3 distinct counts.", classification="OBSERVATIONAL",
            sample_size=el.detail["distinct_counts"], argued_direction="both",
            financial_relevance="0, 1 or 2 moves ($1,800 each).")
        hyp = self.claim(
            "supporting", 2, [], target_investment="INV-PROMO",
            target_assumption="A08_promo_excess_theo_per_day",
            statement="Promotion-day gains may be pulled forward from adjacent days rather than "
                      "be new demand (displacement).",
            action=Action.REQUEST_EVIDENCE, classification="HYPOTHESIS",
            financial_relevance="Would lower net promotion uplift.")
        return [primary, hyp]


class OperationsChief(Agent):
    def review_proposal(self, machine_ids: list[str]) -> list[Claim]:
        out = []
        for mid in machine_ids:
            e = self.t("machine_exposure", machine_id=mid)
            ret = e.detail["retire_date"]
            out.append(self._review_claim(
                mid, "exposure", e,
                f"{mid}: {int(e.value)} active days, availability "
                f"{e.detail['availability']:.1%}" + (f"; retired {ret}: nothing to replace."
                                                    if ret else "."),
                Action.CHALLENGE if ret or e.value < 150 else Action.SUPPORT,
                sample_size=int(e.value)))
            h = self.t("machine_hit_total", machine_id=mid)
            anomaly = h.value > 4.656  # Step 1 rule: Bonferroni p < 0.001 over 310 machines
            out.append(self._review_claim(
                mid, "hit_rate", h,
                f"{mid}: payout frequency z {h.value:.1f} vs configured game math"
                + (": a payout fault; inspect instead of replacing." if anomaly else
                   ": consistent with configuration."),
                Action.CHALLENGE if anomaly else Action.SUPPORT,
                sample_size=h.detail["spins"]))
        return out

    def investigate(self, model: Any) -> list[Claim]:
        hz, st = self.t("machine_monthly_hit_z", machine_id="M-1158"), self.t("tech_staffing")
        mt = self.t("maintenance_fault_effect", manufacturer="Ridgeline")
        primary = self.claim(
            "primary", 1, [hz, st], target_investment="INV-INSPECT-M1158",
            target_assumption="A01_inspect_fix_probability",
            statement=(f"M-1158's payout frequency exceeds its game math in "
                       f"{hz.detail['months_z_gt_3']} of {hz.detail['months']} months (minimum "
                       f"monthly z {hz.value:.1f}): a persistent fault, not luck. Technicians "
                       f"worked {st.value:.1%} of planned shifts, so a 120-minute inspection is "
                       "feasible. The fix probability (break-even 22%) is not identifiable."),
            action=Action.SUPPORT, numeric_result=hz.value, numeric_unit="z",
            limitation="Inspection outcome is information; repair success unmeasured.",
            classification="VERIFIED_FACT_CANDIDATE", sample_size=hz.detail["months"],
            financial_relevance="$1,200 action; ~$200/day modeled loss.")
        support = self.claim(
            "supporting", 2, [mt], target_investment="INV-PREVENT-RIDGELINE",
            target_assumption="A04_preventive_effectiveness",
            statement=(f"Only {mt.detail['all_maintained']} machines ever received scheduled "
                       f"maintenance ({mt.detail['this_manufacturer']} Ridgeline): far too few "
                       "to support the >86% downtime recovery Ridgeline maintenance needs."),
            action=Action.CHALLENGE, numeric_result=mt.value, numeric_unit=mt.unit,
            classification="OBSERVATIONAL", sample_size=mt.detail["all_maintained"],
            argued_direction="low", financial_relevance="$9,000 action.")
        return [primary, support]


def _demand_review(self: Agent, machine_ids: list[str]) -> list[Claim]:
    out = []
    for mid in machine_ids:
        r = self.t("machine_peer_index", machine_id=mid)
        d = r.detail
        out.append(self._review_claim(
            mid, "location", r,
            f"{mid}: earns {r.value:.2f}x its same-game peers in {d['zone_id']}; the zone runs "
            f"at {d['zone_vs_floor']:.2f}x the floor and its game at {d['config_vs_zone']:.2f}x "
            "the zone." + (" Weakness is location/configuration, not the machine."
                           if r.value >= 0.9 else " Weak even against its peers."),
            Action.CHALLENGE if r.value >= 0.9 else Action.SUPPORT,
            alternative_explanation="location and game configuration", sample_size=181))
    return out


DemandStrategist.review_proposal = _demand_review  # type: ignore[method-assign]


class GuestAnalyst(Agent):
    def investigate(self, model: Any) -> list[Claim]:
        pe = self.t("post_event_carded_change")
        disp_per_promo_day = (abs(min(pe.value, 0.0)) * model.facts["carded_theo_per_day"]
                              * 7 / 3)
        adjusted = model.assumptions["A08_promo_excess_theo_per_day"].value - disp_per_promo_day
        primary = self.claim(
            "primary", 1, [pe], target_investment="INV-PROMO",
            target_assumption="A08_promo_excess_theo_per_day",
            statement=(f"Carded theo fell {abs(pe.value):.1%} in the 7 days after both property "
                       f"promotions vs the same weekdays 3-4 weeks earlier. Netting this "
                       f"possible displacement ({disp_per_promo_day:,.0f}/promo-day) gives "
                       f"${adjusted:,.0f}/day excess."),
            action=Action.PROPOSE_SCENARIO, numeric_result=pe.value, numeric_unit="fraction",
            alternative_explanation="Post-event weeks may be seasonally weaker; tracked play "
                                    "only (65.8% of coin-in).",
            limitation="Two events; carded guests only.", classification="OBSERVATIONAL",
            sample_size=2, argued_direction="low",
            financial_relevance="Lowers net promotion uplift.",
            proposed_change=ProposedChange(
                assumption_id="A08_promo_excess_theo_per_day", value=adjusted, unit="USD/day",
                basis="tool:post_event_carded_change x carded_theo_per_day x 7/3"))
        return [primary]

    def respond(self, msg: Message, claims: dict[str, Claim], model: Any) -> list[Reply]:
        c = claims.get(msg.origin_claim_id)
        if c and c.target_assumption == "A08_promo_excess_theo_per_day" and \
                c.classification == "HYPOTHESIS":
            own = stable_id("CLM", self.run_id, self.agent_id, "primary", 1)
            return [Reply(MsgType.ACKNOWLEDGE, msg.sender_agent_id,
                          "Displacement is already measured in my independent finding "
                          f"{own}; your hypothesis adds no independent evidence.",
                          about_claim_id=own)]
        return super().respond(msg, claims, model)


class LoyaltyStrategist(Agent):
    def investigate(self, model: Any) -> list[Claim]:
        cr = self.t("promo_comp_ratio")
        base = model.facts["floor_comp_cost_per_theo"]
        gross = model.assumptions["A08_promo_excess_theo_per_day"].value * 3
        delta_usd = (cr.detail["promo"] - base) * gross
        primary = self.claim(
            "primary", 1, [cr], target_investment="INV-PROMO",
            target_assumption="A08_promo_excess_theo_per_day",
            statement=(f"Comp cost per theo on promotion days is {cr.detail['promo']:.3%} vs "
                       f"{cr.detail['other']:.3%} otherwise; the model already charges "
                       f"{base:.3%}. Extra comps change a promotion weekend by about "
                       f"${-delta_usd:,.0f}, too little to remove its modeled advantage."),
            action=Action.SUPPORT, numeric_result=cr.value, numeric_unit=cr.unit,
            limitation=f"{cr.detail['promo_days']} promotion days.",
            classification="VERIFIED_FACT_CANDIDATE", sample_size=cr.detail["promo_days"],
            financial_relevance="Promotion contribution factor.")
        hyp = self.claim(
            "supporting", 2, [], target_investment="COMP",
            target_assumption="A07_comp_cost_saving_rate",
            statement="The 7.6% rise in comp cost per day may have been caused by promotional "
                      "activity, which would make promotions costlier than modeled.",
            action=Action.REQUEST_EVIDENCE, classification="HYPOTHESIS", causal_claim=True,
            financial_relevance="Would lower promotion net benefit.")
        return [primary, hyp]

    def respond(self, msg: Message, claims: dict[str, Claim], model: Any) -> list[Reply]:
        own_hyp = stable_id("CLM", self.run_id, self.agent_id, "supporting", 2)
        if msg.message_type == MsgType.COUNTERCLAIM and msg.origin_claim_id == own_hyp:
            r = self.t("comp_change_date")  # independent re-check before retracting
            if r.detail["change_date"] < r.detail["next_property_promo_start"]:
                return [Reply(MsgType.RETRACT, msg.sender_agent_id,
                              "Retracting: comp cost rose from the 2025-05-01 policy change, "
                              "before any property promotion.", about_claim_id=own_hyp,
                              retract_claim_id=own_hyp)]
        return super().respond(msg, claims, model)


class CFO(Agent):
    def investigate(self, model: Any) -> list[Claim]:
        pc = self.t("portfolio_comparison")
        e, c = pc.detail["evidence"], pc.detail["conditional"]
        primary = self.claim(
            "primary", 1, [pc], target_investment="PORTFOLIO", target_assumption=None,
            statement=(f"The conditional portfolio costs ${pc.detail['extra_cost']:,.0f} more "
                       f"than the evidence portfolio for ${pc.value:,.0f} more modeled "
                       "contribution, all from assumption-required lines (inspection fix "
                       "probability, move demand transfer). Fund it only with a measurement "
                       "plan for those two assumptions."),
            action=Action.FLAG_UNCERTAINTY, numeric_result=pc.value, numeric_unit="USD",
            limitation="Modeled contribution, not realised profit.",
            classification="VERIFIED_FACT_CANDIDATE",
            financial_relevance=f"{e[0]} (${e[1]:,.0f}) vs {c[0]} (${c[1]:,.0f})")
        return [primary]

    def respond(self, msg: Message, claims: dict[str, Claim], model: Any) -> list[Reply]:
        c = claims.get(msg.origin_claim_id)
        if c and c.proposed_change and msg.message_type in (MsgType.WHISPER,
                                                             MsgType.REQUEST_CHECK):
            p = c.proposed_change
            r = self.t("reoptimise_with", assumption_id=p.assumption_id, value=f"{p.value:.6f}")
            changed = r.detail["evidence"] != r.detail["evidence_base"]
            stmt = (f"If {p.assumption_id} = {p.value:,.0f} {p.unit}, the evidence portfolio "
                    f"becomes {r.detail['evidence']} (was {r.detail['evidence_base']}; "
                    f"{r.value:+,.0f} USD modeled).")
            esc = self.claim("gossip", 20 + msg.sequence, [r], target_investment="PORTFOLIO",
                             target_assumption=p.assumption_id, statement=stmt,
                             action=Action.FLAG_UNCERTAINTY, numeric_result=r.value,
                             numeric_unit="USD", classification="VERIFIED_FACT_CANDIDATE",
                             origin_claim_id=c.claim_id, depends_on=(c.claim_id,),
                             round_number=msg.round_number + 1,
                             financial_relevance="Portfolio consequence of the challenge.")
            mtype = MsgType.ESCALATE if changed else MsgType.ACKNOWLEDGE
            return [Reply(mtype, "VERIFIER" if changed else msg.sender_agent_id, stmt, esc)]
        if c and c.classification == "HYPOTHESIS":  # forward for a check, origin preserved
            return [Reply(MsgType.REQUEST_CHECK, "AG1_STATISTICIAN",
                          f"Forwarding unverified hypothesis {c.claim_id} for a timing check.",
                          about_claim_id=c.claim_id)]
        return super().respond(msg, claims, model)


def _cfo_review(self: Agent, machine_ids: list[str]) -> list[Claim]:
    out = []
    for mid in machine_ids:
        try:
            r = self.t("replacement_lease_net", machine_id=mid, case="best_case")
        except ValueError:
            continue  # not evaluable (retired): Operations Chief covers it
        out.append(self._review_claim(
            mid, "economics", r,
            f"Replacing {mid} with a leased title nets ${r.value:,.0f} in July even if the new "
            "title matches the best one ever observed in its zone"
            + (": not worth replacing." if r.value <= 0 else ": positive only in the best case."),
            Action.CHALLENGE if r.value <= 0 else Action.FLAG_UNCERTAINTY))
    return out


CFO.review_proposal = _cfo_review  # type: ignore[method-assign]


def build_agents() -> list[Agent]:
    return [
        Statistician("AG1_STATISTICIAN", "Statistician",
                     "Detect statistical weaknesses that could change an investment decision.",
                     "Two promotion observations cannot support a reliable uplift estimate.",
                     ("promo_event_excess", "weekend_noise_sd", "comp_change_date", "machine_luck"),
                     ("A08_promo_excess_theo_per_day", "statistics", "timing"),
                     "Evidence is below a break-even or indistinguishable from noise."),
        DemandStrategist("AG2_DEMAND", "Demand Strategist",
                         "Test whether machine moves create incremental demand.",
                         "Moving machines into Center Pit may redistribute existing play.",
                         ("zone_occupancy", "zone_count_elasticity", "machine_peer_index"),
                         ("A09_move_location_transfer", "A03_wayfinding_net_uplift", "demand"),
                         "Transfer evidence crosses the 20-21% boundary."),
        OperationsChief("AG3_OPERATIONS", "Operations Chief",
                        "Test feasibility and recoverable benefits of operational actions.",
                        "Inspection or maintenance benefits need unrealistic success rates.",
                        ("machine_monthly_hit_z", "tech_staffing", "maintenance_fault_effect",
                         "machine_exposure", "machine_hit_total"),
                        ("A01_inspect_fix_probability", "A04_preventive_effectiveness",
                         "A05_tech_downtime_reduction", "operations"),
                        "A required success rate is above anything observed."),
        GuestAnalyst("AG4_GUEST", "Guest Analyst",
                     "Test whether promotion gains are net new guest activity.",
                     "Promotion gains may be displaced visits rather than new demand.",
                     ("post_event_carded_change",),
                     ("A08_promo_excess_theo_per_day", "displacement", "guests"),
                     "Post-event activity falls by a financially material amount."),
        LoyaltyStrategist("AG5_LOYALTY", "Loyalty Strategist",
                          "Challenge promotional contribution and comp assumptions.",
                          "Extra comp costs could eliminate the promotion advantage.",
                          ("promo_comp_ratio", "comp_change_date"),
                          ("A06_comp_play_response", "A07_comp_cost_saving_rate", "comp"),
                          "Comp cost per theo on promotion days exceeds the modeled rate."),
        CFO("AG6_CFO", "CFO",
            "Challenge prioritisation and financial risk.",
            "The $34,800 conditional portfolio does not justify its extra uncertainty.",
            ("portfolio_comparison", "reoptimise_with", "replacement_lease_net"),
            ("portfolio", "financial_consequence", "A08_promo_excess_theo_per_day"),
            "A challenge changes a baseline portfolio."),
    ]
