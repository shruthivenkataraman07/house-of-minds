"""Ask the House: deterministic, schema-constrained intent router (no LLM, no SQL).

question -> normalise -> safety screen -> entity extraction validated against the data ->
ranked intent rules -> allowlisted action with validated args -> answer composed only from
contract fields (period, evidence reference, uncertainty). Ported from the dashboard's
original TypeScript router; behaviour and test cases are preserved.
"""

from __future__ import annotations

import re
from statistics import median
from typing import Any

from .dashboard import ZONE_NAMES, floor_totals
from .source import DataSource

ACTIONS = (
    "select_entity",
    "set_filters",
    "compare_portfolios",
    "get_evidence",
    "explain_reversal",
    "open_validation",
    "open_council",
    "open_answers",
)
VIEWS = (
    "overview",
    "machines",
    "operations",
    "council",
    "scenarios",
    "investment",
    "evidence",
    "validation",
    "answers",
)
OFFICIAL = "Jan 1–Jun 30, 2025 (official window)"
HZ = "Jul 1–30, 2025 (modeled contribution, not realized profit)"

SQL = re.compile(
    r"\b(select\s+.+\s+from|drop\s+table|insert\s+into|delete\s+from|update\s+\w+\s+set|"
    r"union\s+select|;\s*--|truncate|alter\s+table)\b",
    re.I,
)
WRITE = re.compile(
    r"\b(delete|drop|modify|change|update|overwrite|edit|set|write|insert|remove|alter)\b"
    r".*\b(data|table|record|row|value|number|verdict|database|dataset|machine|figure)s?\b",
    re.I,
)
PII = re.compile(
    r"\b(player|guest)\s*(id|name|email|phone|address)\b|\bwho (is|are) the (biggest|heaviest)\b"
    r"|\btarget\b.*\blos(ers|ing)\b",
    re.I,
)
ZONE_SYN = {
    "back forty": "Z-B40",
    "b40": "Z-B40",
    "center pit": "Z-PIT",
    "centre pit": "Z-PIT",
    "main entrance": "Z-ENT",
    "entrance": "Z-ENT",
    "high limit": "Z-HL",
    "high-limit": "Z-HL",
    "bar row": "Z-BAR",
    "garage": "Z-GAR",
    "hotel": "Z-HTL",
}


def _usd(v: Any, signed: bool = False) -> str:
    if v is None:
        return "n/a"
    x = float(v)
    s = f"${abs(x):,.0f}"
    if x < 0:
        return f"−{s}"
    return f"+{s}" if signed and x > 0 else s


def _pct(v: Any, d: int = 1) -> str:
    return "n/a" if v is None else f"{float(v) * 100:.{d}f}%"


def _answer(
    status: str,
    intent: str,
    conclusion: str,
    *,
    support: list[str] | None = None,
    period: str = OFFICIAL,
    evidence: str = "",
    uncertainty: str | None = None,
    premise: str | None = None,
    action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if action is not None:
        assert action["type"] in ACTIONS and action["view"] in VIEWS
    return {
        "status": status,
        "intent": intent,
        "conclusion": conclusion,
        "support": support or [],
        "period": period,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "premise_correction": premise,
        "action": action,
    }


VERDICT_LABEL = {
    "REPLACE_NONE": "Replace none",
    "REPLACE_ALL": "Replace all",
    "REPLACE_SOME": "Replace some",
    "INSUFFICIENT_EVIDENCE": "insufficient evidence",
    "RETIRED_ALREADY": "already retired",
    "DO_NOT_REPLACE_INSPECT": "inspect, don't replace",
    "DO_NOT_REPLACE_NOT_ECONOMIC": "not economic to replace",
    "DO_NOT_REPLACE_EXPOSURE": "limited floor time",
    "REPLACE_JUSTIFIED_CONDITIONAL": "replace (conditional)",
}
ACTION_LABEL = {
    "INV-PROMO": "promotion weekend",
    "INV-INSPECT-M1158": "inspection of M-1158",
    "INV-MOVE-M-1154-Z-PIT": "move M-1154 to Center Pit",
    "INV-MOVE-M-1184-Z-PIT": "move M-1184 to Center Pit",
}
MONTHS = {
    m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june"], start=1)
}
MONTH_DAYS = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30}


def _verdict(code: str) -> str:
    return VERDICT_LABEL.get(code, code.replace("_", " ").lower())


def _plan(alloc: str) -> str:
    """Business wording for an optimizer allocation string such as INV-PROMOx2."""
    if not alloc or alloc == "HOLD":
        return "no spending (hold)"
    out = []
    for part in alloc.split(";"):
        m = re.match(r"^(.*)x(\d+)$", part)
        name, qty = (m.group(1), int(m.group(2))) if m else (part, 1)
        label = ACTION_LABEL.get(name, name.replace("INV-", "").lower())
        out.append(f"{qty} {label}s" if qty > 1 else label)
    return ", ".join(out)


def _act(t: str, view: str, **args: Any) -> dict[str, Any]:
    return {"type": t, "view": view, "args": {k: v for k, v in args.items() if v is not None}}


def ask(question: str, src: DataSource, machine_context: str | None = None) -> dict[str, Any]:
    q = re.sub(r"\s+", " ", question.lower().replace("’", "'")).strip()[:400]
    if not q:
        return _answer(
            "UNSUPPORTED",
            "none",
            "Ask about machines, the $100K plan, the council, "
            "demand, downtime, players, comps or the forecast.",
        )
    if SQL.search(q):
        return _answer(
            "REFUSED",
            "arbitrary_sql",
            "Ask the House does not run SQL; it answers "
            "from the validated data through fixed read-only actions.",
            evidence="Allowlisted actions: " + ", ".join(ACTIONS),
        )
    if WRITE.search(q) and not re.search(r"\bwhat (if|happens)\b|\bscenario\b|\bwould\b", q):
        return _answer(
            "REFUSED",
            "write",
            "Ask the House is read-only: it cannot change data, verdicts or tables.",
            evidence="No write actions exist.",
        )
    if PII.search(q):
        return _answer(
            "REFUSED",
            "individual_player",
            "Player data is shown only as tier "
            "aggregates; individual guests are never identified or targeted.",
            evidence="ch_player_outcomes_by_tier",
            action=_act("set_filters", "operations", tab="players"),
        )

    machine_ids = {m["machine_id"] for m in src.get("dash_machine_intelligence")}
    ids = list(dict.fromkeys("M-" + re.sub(r"\D", "", m) for m in re.findall(r"\bm-?\d{4}\b", q)))
    for i in ids:
        if i not in machine_ids:
            return _answer(
                "UNAVAILABLE",
                "select_entity",
                f"Machine {i} is not in the data "
                "(310 machines, M-1001…); no figures are shown for an unknown ID.",
                evidence="dash_machine_intelligence",
            )
    bank_id = None
    bm = re.search(r"\bbank\s*-?\s*(b-?\d{1,3}|\d{1,3})\b", q)
    if bm:
        want = re.sub(r"^b-?", "", bm.group(1))
        cand = next(
            (
                b["bank_id"]
                for b in src.get("bank_day")["banks"]
                if re.sub(r"^b-?", "", b["bank_id"].lower()) == want
            ),
            None,
        )
        if cand is None:
            return _answer(
                "UNAVAILABLE",
                "select_entity",
                f'Bank "{bm.group(1).upper()}" is not in the data.',
                evidence="bank_day",
            )
        bank_id = cand
    zone_id = next((z for k, z in ZONE_SYN.items() if k in q), None)
    zm = re.search(r"\bz-[a-z0-9]+\b", q)
    if zm and zm.group(0).upper() in ZONE_NAMES:
        zone_id = zm.group(0).upper()

    refers = re.search(r"\b(it|this machine|that machine|this one|that one)\b", q)
    if not ids and refers and re.search(r"machine|it\b", q):
        if machine_context and machine_context in machine_ids:
            ids.append(machine_context)
        else:
            return _answer(
                "AMBIGUOUS",
                "select_entity",
                "Which machine? None is selected; name "
                "one (for example M-5076) or select it in Machines.",
            )
    if len(ids) > 1 and not re.search(r"compare|vs|versus", q):
        return _answer(
            "AMBIGUOUS",
            "select_entity",
            f"Several machines named ({', '.join(ids)}); ask about one at a time.",
        )

    v = src.get("ch_executive_verdict")[0]
    pf = {p["option"]: p for p in src.get("ch_portfolio_comparison")}
    mgr, hom = pf.get("manager_proposal_lease", {}), pf.get(v["recommended_option"], {})
    pa = src.get("audit_c_promotion_portfolio")
    sc = {s["scenario"]: s for s in pa["scenarios"]}
    rob = src.get("audit_b4_robustness_matrix")
    pb = [r["payback_days_after_install_at_A10_0.5"] for r in rob]
    ss = [r["steady_state_breakeven_A10"] for r in rob]
    payback = f"{round(min(pb))}–{round(max(pb))} days"
    ss_range = f"{round(min(ss) * 100)}–{round(max(ss) * 100)}%"
    b10 = sorted(src.get("ch_machine_investigation"), key=lambda m: m["manager_rank"])

    if (
        re.search(r"forecast|holdout|holt|model|predict|baseline|mlflow|validation|reliab", q)
        and not ids
    ):
        fc = {f["subset"]: f for f in src.get("forecast_baseline_comparison")}
        a, e = fc["all"], fc["event_days"]
        return _answer(
            "OK",
            "open_validation",
            f"Holt-Winters beat the weekday-mean baseline on the holdout (MAE {_usd(a['candidate_mae'])} "
            f"vs {_usd(a['baseline_mae'])}/day, {a['mae_improvement_pct']:.1f}% better) but was worse on "
            f"event days ({e['mae_improvement_pct']:.1f}%).",
            support=[
                f"80% interval coverage {_pct(a['candidate_coverage80'])} overall, "
                f"{_pct(e['candidate_coverage80'])} on event days.",
                "Stored in Delta tables; no MLflow model exists.",
            ],
            period="Train Jan–Mar, validate Apr, holdout May 1–Jun 30, 2025",
            evidence="forecast_baseline_comparison · dash_model_evaluation",
            uncertainty="The one decision the model changes (weak-case promotions) depends on "
            "event-day accuracy, where it underperforms.",
            action=_act("open_validation", "validation"),
        )

    if len(ids) == 1:
        mid = ids[0]
        row = next(m for m in src.get("dash_machine_intelligence") if m["machine_id"] == mid)
        inv = next((m for m in b10 if m["machine_id"] == mid), None)
        r = next((x for x in rob if x["machine_id"] == mid), None)
        cand = next(
            (c for c in src.get("ch_replacement_candidates") if c["machine_id"] == mid), None
        )
        support = [
            f"House win {_usd(row['house_win_usd'])} vs theo {_usd(row['theo_usd'])} (luck z "
            f"{row['luck_z']:.2f}); {ZONE_NAMES.get(row['zone_id'], row['zone_id'])}, {row['config_id']}.",
            f"Theo per available hour ${row['theo_per_available_hour']:.2f}; raw rank {row['rank_raw']}, "
            f"vs same-game peers {row['rank_vs_peers']} of 310 (1 = weakest).",
        ]
        if inv:
            conclusion = (
                f"{mid} is #{inv['manager_rank']} on the manager's list. Verdict: "
                f"{_verdict(inv['verdict']).capitalize()}. {inv['recommended_alternative'][:1].upper()}{inv['recommended_alternative'][1:]}."
            )
            if inv["lease_net_planning_usd"] is not None:
                support.append(
                    f"July lease net {_usd(inv['lease_net_planning_usd'], True)} at the planning "
                    f"value, {_usd(inv['lease_net_best_case_usd'], True)} at the zone's best title."
                )
            if inv["retire_date"]:
                support.append(f"Retired {str(inv['retire_date'])[:10]}.")
            if inv["verdict"] == "DO_NOT_REPLACE_INSPECT":
                support.append(
                    f"Hit-rate z = {inv['hit_rate_z']:.1f} vs game math (Bonferroni p < 0.001)."
                )
            support.append(
                f"Council: {_verdict(inv['council_verdict'])} ({'agrees' if inv['council_agrees'] else 'disagrees'})."
            )
        else:
            conclusion = f"{mid} is not on the manager's bottom-10 list." + (
                f" As a replacement candidate it nets {_usd(cand['lease_net_planning_usd'], True)} at the planning "
                f"value and {_usd(cand['lease_net_best_case_usd'], True)} in the best case."
                if cand
                else " It is not a replacement candidate (no positive best case)."
            )
        unc = (
            f"Robustness {r['robustness']}: conservative {_usd(r['conservative_A10_0.25_cann_0.25'], True)}, "
            f"base {_usd(r['base_A10_0.5'], True)}, optimistic {_usd(r['optimistic_A10_1.0'], True)}; "
            f"July break-even needs {r['breakeven_A10_july'] * 100:.0f}% gap capture."
            if r
            else None
        )
        return _answer(
            "OK",
            "select_entity",
            conclusion,
            support=support,
            period=f"{OFFICIAL}; economics {HZ}",
            evidence=f"ch_machine_investigation · {inv['council_deciding_claims'] or ''}"
            if inv
            else "dash_machine_intelligence",
            uncertainty=unc,
            action=_act("select_entity", "machines", machine_id=mid),
        )

    if re.search(
        r"zero|no (promo|uplift)|without (the )?promo|promo.*(fail|nothing|zero)|uplift.*(zero|0\b)",
        q,
    ):
        z, w = sc["zero_uplift"], sc["weakest_event"]
        return _answer(
            "OK",
            "explain_reversal",
            f"At zero uplift the two weekends lose their cost: the recommended plan nets "
            f"{_usd(z['original_evidence'], True)}. Without promotions the best plan is "
            f"{_usd(z['conditional_without_promo'], True)} (inspect M-1158 + 2 moves) or hold.",
            support=[
                f"Break-even uplift {_usd(pa['break_even_A08'])}/day; weakest observed event "
                f"{_usd(pa['a08']['low'])}/day gives {_usd(w['original_evidence'], True)}.",
                f"Base case: {_usd(sc['base_mean']['original_evidence'], True)}.",
            ],
            period=HZ,
            evidence="audit c_promotion_portfolio · decision_model_impact",
            uncertainty="Uplift rests on 2 events with no control group (associational).",
            action=_act("explain_reversal", "scenarios", scenario="zero_uplift"),
        )

    if re.search(r"\b(answers?|summary|summarize|six questions|conclusions?|final)\b", q):
        return _answer(
            "OK",
            "open_answers",
            "The Answers tab gives one evidence-backed conclusion for each of the six questions.",
            support=[
                f"Headline: {_verdict(v['answer'])}; recommended plan {_usd(v['recommended_net_usd'], True)}."
            ],
            period=f"{OFFICIAL}; economics {HZ}",
            evidence="ch_executive_verdict",
            action=_act("open_answers", "answers"),
        )

    if re.search(r"council|agent|challeng|object|statistician|cfo|whisper|debate", q):
        cr = src.get("ch_council_manager_review")
        changed = sum(1 for m in b10 if m["council_verdict"] != m["verdict"])
        premise = (
            "Premise check: the council did not reject the promotion plan; it flagged the uplift "
            "assumption as a fragility and kept it."
            if re.search(r"reject|overturn|veto|block|disagree", q)
            and re.search(r"promo|portfolio|plan|recommend", q)
            else None
        )
        return _answer(
            "OK",
            "open_council",
            f"The council reviewed the manager's proposal with {len(cr)} claims "
            f"({sum(c['verdict'] == 'VERIFIED' for c in cr)} verified) and matched the analytic verdict "
            f'on {10 - changed}/10 machines, overturning "replace" for all 10.',
            support=[
                "Checks: luck (Statistician), location (Demand), exposure and payout faults "
                "(Operations), lease economics (CFO).",
                "In the portfolio hearing one causal claim was retracted and promotion uplift was "
                "flagged; the recommended portfolio did not change.",
            ],
            evidence="ch_council_manager_review · dash_council_activity",
            uncertainty="Agents are rule-based and share the analytic rules: agreement is a "
            "reproducibility check, not independent confirmation.",
            premise=premise,
            action=_act("open_council", "council"),
        )

    if re.search(
        r"compare|manager'?s plan|versus|vs\.?|alternative|which plan|better plan|portfolio", q
    ):
        return _answer(
            "OK",
            "compare_portfolios",
            f"Manager's plan: {_usd(mgr.get('cost_usd'))} for {_usd(mgr.get('expected_net_benefit_usd'), True)} "
            f"modeled net. House of Minds: {_usd(hom.get('cost_usd'))} for "
            f"{_usd(hom.get('expected_net_benefit_usd'), True)}.",
            support=[
                f"Manager range {_usd(mgr.get('net_low_usd'), True)} to {_usd(mgr.get('net_high_usd'), True)}.",
                f"House of Minds range {_usd(hom.get('net_low_usd'), True)} to "
                f"{_usd(hom.get('net_high_usd'), True)} (promotion uplift).",
                "Buying 10 machines ($220,000) breaks the $100,000 budget.",
            ],
            period=HZ,
            evidence="ch_portfolio_comparison",
            uncertainty="The recommended plan is negative at the weakest observed promotion.",
            action=_act("compare_portfolios", "scenarios"),
        )

    if re.search(r"break.?even|revers|flip|threshold|what would change|sensitiv|robust", q):
        return _answer(
            "OK",
            "explain_reversal",
            f"The plan flips to HOLD if promotion excess theo falls below {_usd(pa['break_even_A08'])}/day; "
            f"the weakest observed event ({_usd(pa['a08']['low'])}/day) is just below it.",
            support=[
                '"Replace none" holds within July under every tested variant.',
                f"After July, replacements at the planning value would pay back in {payback}.",
            ],
            period=HZ,
            evidence="audit b4_robustness_matrix · dash_scenario_surface",
            action=_act("explain_reversal", "scenarios", tab="reversals"),
        )

    if re.search(r"downtime|outage|broke|fault|repair|availability|maintenance", q):
        dt = src.get("ch_downtime_economics")
        hours = sum(float(r["downtime_hours"]) for r in dt)
        risk = sum(float(r["theo_at_risk_usd"]) for r in dt)
        top = max(src.get("ch_downtime_by_hour"), key=lambda r: float(r["downtime_hours"]))
        worst = sorted(b10, key=lambda m: -m["downtime_hours"])[:3]
        by_zone: dict[str, float] = {}
        for r in dt:
            by_zone[r["zone_id"]] = by_zone.get(r["zone_id"], 0.0) + float(r["downtime_hours"])
        zmax = max(by_zone, key=lambda z: by_zone[z])
        bank_note = (
            [
                f"Downtime is recorded by zone, not bank; the most downtime was in {ZONE_NAMES.get(zmax, zmax)} ({by_zone[zmax]:,.0f} h)."
            ]
            if "bank" in q
            else []
        )
        return _answer(
            "OK",
            "set_filters",
            f"{hours:,.0f} machine-hours of downtime put {_usd(risk)} of theoretical win at risk "
            "(opportunity, not guaranteed loss).",
            support=bank_note
            + [
                f"Worst hour: {int(top['local_hour']):02d}:00 ({float(top['downtime_hours']):.0f} h).",
                "Manager-list machines with most downtime: "
                + ", ".join(f"{m['machine_id']} {m['downtime_hours']:.0f} h" for m in worst)
                + ".",
            ],
            evidence="ch_downtime_economics · ch_downtime_by_hour",
            uncertainty="Assumes lost play does not move to other machines.",
            action=_act("set_filters", "operations", tab="downtime", zone_id=zone_id),
        )

    month = next(
        (
            i
            for name, i in MONTHS.items()
            # "may" is also a verb: only "in May" / "May 2025" count as the month
            if (
                re.search(r"\bin may\b|\bmay 2025\b", q)
                if name == "may"
                else re.search(rf"\b{name[:3]}(?:{name[3:]})?\b", q)
            )
        ),
        None,
    )
    if month and re.search(r"demand|traffic|coin.?in|wager|busy|show|visits", q):
        start, end = f"2025-{month:02d}-01", f"2025-{month:02d}-{MONTH_DAYS[month]:02d}"
        t = floor_totals(src, start, end)
        full = floor_totals(src, "2025-01-01", "2025-06-30")
        per_day, avg = t["coin_in_per_day_usd"], full["coin_in_per_day_usd"]
        return _answer(
            "OK",
            "set_filters",
            f"{start[:7]}: {_usd(t['coin_in_usd'])} wagered over {t['days']} gaming days "
            f"({_usd(per_day)} per day, {(per_day / avg - 1) * 100:+.1f}% vs the Jan–Jun daily average).",
            support=[
                f"Casino win {_usd(t['house_win_usd'])}; share of wagers kept {_pct(t['hold'], 2)} (ratio of sums).",
                f"Wagered per available machine-hour {_usd(t['coin_in_per_available_hour_usd'])}.",
            ],
            period=f"{start}..{end} (exploratory; verdicts stay on Jan–Jun)",
            evidence="property_day (daily grain) · ch_floor_demand_monthly",
            action=_act("set_filters", "operations", tab="demand", start=start, end=end),
        )

    if re.search(r"demand|traffic|coin.?in|zone|busy|visits|walkway", q) or zone_id or bank_id:
        ex = src.get("ch_demand_explanations")
        e0 = ex[0]
        return _answer(
            "OK",
            "set_filters",
            f"{e0['change']}: {float(e0['observed_pct']):.1f}%; per available machine-hour "
            f"{float(e0['result_pct']):.1f}%, so fewer machines do not explain it.",
            support=[
                f"Filtered to {ZONE_NAMES[zone_id]}."
                if zone_id
                else f"{ex[1]['change']}: {float(ex[1]['observed_pct']):.1f}% ({ex[1]['conclusion']})."
            ],
            evidence="ch_floor_demand_monthly · ch_zone_demand · ch_demand_explanations",
            uncertainty="Traffic counters count crossings; offline hours are missing, not zero.",
            action=_act(
                "set_filters",
                "operations",
                tab="banks" if bank_id else "demand",
                zone_id=zone_id,
                bank_id=bank_id,
            ),
        )

    if re.search(r"loyal|tier|guest|player|tracked|comp|points|segment", q):
        p = src.get("ch_player_outcomes")[0]
        comps = bool(re.search(r"comp|points", q))
        c = src.get("ch_loyalty_comps")
        c0, cn = c[0], c[-1]
        concl = (
            f"Points per comp dollar went from {float(c0['points_per_comp_usd']):.1f} ({c0['month']}) to "
            f"{float(cn['points_per_comp_usd']):.1f} ({cn['month']}); comp cost per carded theo from "
            f"{_pct(c0['comp_cost_per_carded_theo'], 2)} to {_pct(cn['comp_cost_per_carded_theo'], 2)}."
            if comps
            else f"Tracked players wagered {_usd(p['tracked_coin_in_usd'])} and lost {_usd(-float(p['tracked_player_net_usd']))} "
            f"net; {_pct(p['share_players_ahead'])} finished ahead; the top 10% generate "
            f"{_pct(p['top10pct_share_of_theo'])} of tracked theo."
        )
        return _answer(
            "OK",
            "set_filters",
            concl,
            support=[
                f"{t['tier']}: {int(t['players']):,} players, {_usd(t['theo'])} theo"
                for t in src.get("ch_player_outcomes_by_tier")
            ],
            evidence="ch_loyalty_comps"
            if comps
            else "ch_player_outcomes · ch_player_outcomes_by_tier",
            uncertainty=f"Carded play only ({_pct(p['carded_share_of_all_coin_in'])} of coin-in); "
            "not comparable with all-play meter totals.",
            action=_act("set_filters", "operations", tab="comps" if comps else "players"),
        )

    if re.search(r"evidence|source|prove|trace|passport|how do (we|you) know|support", q):
        pp = next(
            (
                x
                for x in src.get("dash_decision_passports")
                if x["portfolio_mode"] == "evidence_supported"
            ),
            None,
        )
        cl = src.get("dash_evidence_validation")
        return _answer(
            "OK",
            "get_evidence",
            f"The recommendation ({_plan(v['recommended_allocation'])}) is documented in passport "
            f"{pp['passport_id'] if pp else 'n/a'}: cost, effect, assumptions, council claims and reversals.",
            support=[
                f"Effect classification: {pp['effect_classification'] if pp else 'n/a'}.",
                f"{len(cl)} registered claims; {sum(c['verification_status'] == 'PASS' for c in cl)} pass.",
            ],
            period=HZ,
            evidence=pp["passport_id"] if pp else "dash_decision_passports",
            action=_act("get_evidence", "evidence", evidence_id=pp["passport_id"] if pp else None),
        )

    if re.search(r"replace|bottom|lowest|worst|10 machines|ten machines|manager", q) or re.search(
        r"\b(all|every)\b", q
    ):
        premise = (
            "Premise check: the evidence does not support replacing these machines."
            if re.search(r"why (should|do) (we|i) replace|replace all", q)
            else None
        )
        pi = median(m["machine_vs_peer_index"] for m in b10)
        return _answer(
            "OK",
            "get_evidence",
            f"{_verdict(v['answer'])}. Of the 10: {v['retired_already']} retired, {v['inspect_instead']} need "
            f"inspection (payout fault), {v['not_economic']} lose money on a lease even with the zone's best "
            f"title, {v['insufficient_evidence']} has insufficient evidence.",
            support=[
                f"Manager's lease plan: {_usd(mgr.get('expected_net_benefit_usd'), True)} for {_usd(mgr.get('cost_usd'))}.",
                f"{sum(m['zone_id'] == 'Z-B40' for m in b10)}/10 sit in Back Forty; median same-game peer index {pi:.2f}.",
                f"Council agreement {v['council_agreement']}/10.",
            ],
            period=f"{OFFICIAL}; economics {HZ}",
            evidence="ch_executive_verdict · ch_machine_investigation",
            uncertainty=f"July only. Longer term, replacements could pay back ({payback}) if a new title "
            f"captures at least {ss_range} of the gap to the zone's best title (unmeasured).",
            premise=premise,
            action=_act("select_entity", "machines"),
        )

    if re.search(r"spend|100k|\$?100,?000|budget|invest|recommend|what should", q):
        return _answer(
            "OK",
            "compare_portfolios",
            f"Spend {_usd(v['recommended_cost_usd'])} on {_plan(v['recommended_allocation'])} (modeled net "
            f"{_usd(v['recommended_net_usd'], True)}) and keep {_usd(100000 - float(v['recommended_cost_usd']))}.",
            support=[
                f"Conditional upside: {_usd(v['conditional_upside_cost_usd'])} for "
                f"{_usd(v['conditional_upside_net_usd'], True)}."
            ],
            period=HZ,
            evidence="ch_portfolio_comparison · dash_decision_passports",
            uncertainty="Promotion uplift is associational (2 events, no control).",
            action=_act("compare_portfolios", "investment"),
        )

    return _answer(
        "UNSUPPORTED",
        "none",
        "Outside what the validated data can answer.",
        support=[
            'Try: "Why not replace the bottom 10?", "Explain M-5076", "What if promotion '
            'uplift is zero?", "How reliable is the forecast?"'
        ],
    )
