"""Step 3: evidence-constrained investment candidates and assumption registry.

Money flow per candidate (USD over the 30-day horizon starting 2025-07-01):

    gross theo gain       = daily theo gain x effective days          (incremental play)
    contribution gain     = gross theo gain x contribution factor     (after revenue-share
                                                                       lease and comps)
    + avoided costs         (e.g. repair cost)
    - downtime cost        = install/maintenance downtime hours x theo/hour x factor
    - investment cost      = official catalog formula (GUIDE section 6)
    = incremental net benefit

Theo (not realised win) is the benefit base: it is luck-free and is what an action can
change. The contribution factor converts theo to the house's share:
    factor = 1 - 0.20 x revenue-share theo share - comp cost per theo
Supplied power/service costs are per machine-day, so they do not scale with play.

Every parameter has a status:
    EVIDENCE_ESTIMATE      computed from official data (may still be associational)
    EVIDENCE_UPPER_BOUND   a data-derived ceiling; used to exclude actions robustly
    ASSUMPTION_REQUIRED    not identifiable from the data; a labelled planning value
                           with a tested range. Never presented as a fact.
    NOT_IDENTIFIABLE       no defensible value; the candidate is excluded from the
                           financial objective and listed, never treated as zero.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from backend.repositories.base import AnalyticsRepository
from optimization.action_catalog import HORIZON_DAYS, HORIZON_START, ActionCatalog

EVIDENCE_ESTIMATE = "EVIDENCE_ESTIMATE"
EVIDENCE_UPPER_BOUND = "EVIDENCE_UPPER_BOUND"
ASSUMPTION_REQUIRED = "ASSUMPTION_REQUIRED"
NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"
NEGATIVE_AT_BEST_CASE = "NEGATIVE_AT_BEST_CASE"  # evidence-robust exclusion
ADMISSIBLE = {EVIDENCE_ESTIMATE, EVIDENCE_UPPER_BOUND}

# Step 2 evidence records (deterministic ids; resolved against evidence_ledger at runtime)
EV = {
    "payout_anomaly": "EV-1C684B792E7B",
    "walkway_closure": "EV-D10316B9740D",
    "downtime": "EV-65ECD7585FD8",
    "comp_change": "EV-ABCA3B586A41",
    "persistence": "EV-955F2384D49D",
    "decomposition": "EV-E7D9F597BA06",
}
REVENUE_SHARE_RATE = 0.20  # cost_rules CR-LEASE-SHARE


@dataclass
class Assumption:
    assumption_id: str
    description: str
    value: float
    low: float
    high: float
    unit: str
    status: str
    source: str
    evidence_ids: list[str]
    causal_status: str
    valid: bool = True

    def as_row(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence_ids"] = ",".join(self.evidence_ids)
        return d


@dataclass
class Candidate:
    candidate_id: str
    action_type: str
    target_entity: str
    max_quantity: int
    eligible: bool
    eligibility_reason: str
    assumptions: list[str]  # assumption ids the benefit depends on
    observed_signal: str
    benefit_status: str  # status of the weakest input
    causal_status: str
    evidence_ids: list[str]
    machines: list[str] = field(default_factory=list)  # for same_machine conflicts
    capacity_group: str | None = None  # shared destination-slot capacity
    notes: str = ""


@dataclass
class InvestmentModel:
    """Inputs (facts + assumptions) and candidates. Economics are pure functions of it."""
    facts: dict[str, float]
    assumptions: dict[str, Assumption]
    candidates: list[Candidate]
    catalog: ActionCatalog
    capacity: dict[str, int]
    scenario_id: str = "baseline"
    lead_delay_days: int = 0
    cost_multiplier: float = 1.0
    demand_multiplier: float = 1.0
    b40_multiplier: float = 1.0

    def a(self, key: str) -> float:
        return self.assumptions[key].value

    def with_assumption(self, key: str, value: float) -> InvestmentModel:
        m = copy.deepcopy(self)
        m.assumptions[key].value = float(value)
        return m

    def fingerprint(self) -> str:
        # 9 significant digits: engines differ in float summation order (~1e-9 relative)
        payload = {"facts": {k: float(f"{v:.9g}") for k, v in self.facts.items()},
                   "assumptions": {k: [v.value, v.valid] for k, v in self.assumptions.items()},
                   "scenario": [self.scenario_id, self.lead_delay_days, self.cost_multiplier,
                                self.demand_multiplier, self.b40_multiplier]}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- timing
def effective_days(lead_days: int, delay: int = 0) -> int:
    return max(0, HORIZON_DAYS - lead_days - delay)


def promo_weekends(lead_days: int, delay: int = 0) -> int:
    """Fri-Sun weekends that start on/after the effective date and end inside the horizon."""
    start = HORIZON_START + timedelta(days=lead_days + delay)
    end = HORIZON_START + timedelta(days=HORIZON_DAYS - 1)
    n, d = 0, start
    while d + timedelta(days=2) <= end:
        if d.weekday() == 4:
            n += 1
        d += timedelta(days=1)
    return n


# --------------------------------------------------------------------------- facts
def load_facts(repo: AnalyticsRepository) -> dict[str, float]:
    """Every number here is computed from official tables (validated in Step 1/2)."""
    q = repo.query_df
    f: dict[str, float] = {}
    c = q("""SELECT sum(m.theo_cents)::DOUBLE / 100 theo,
            sum(m.theo_cents) FILTER (WHERE mc.lease_class = 'leased_revenue_share')::DOUBLE
              / sum(m.theo_cents) revshare_share,
            sum(m.carded_theo_cents)::DOUBLE / 100 carded_theo,
            count(DISTINCT m.gaming_date) n_days
         FROM machine_day m JOIN machines mc USING (machine_id)
         WHERE m.active AND m.gaming_date >= DATE '2025-05-01'""").iloc[0]
    comp = float(repo.scalar("SELECT sum(comp_cost_usd)::DOUBLE FROM property_day "
                             "WHERE gaming_date >= DATE '2025-05-01'"))
    f["floor_comp_cost_per_theo"] = comp / float(c.theo)
    f["floor_revshare_share"] = float(c.revshare_share)
    f["floor_contribution_factor"] = (1 - REVENUE_SHARE_RATE * f["floor_revshare_share"]
                                      - f["floor_comp_cost_per_theo"])
    f["carded_theo_per_day"] = float(c.carded_theo) / float(c.n_days)
    # M-1158 (payout anomaly): owned, so no revenue share
    m = q("""SELECT mc.lease_class, sum(m.theo_cents)::DOUBLE / 100
                / (sum(m.available_seconds) / 3600.0) theo_per_ah,
             (sum(m.theo_cents) - sum(m.house_win_cents))::DOUBLE / 100 / count(*) loss_per_day,
             sqrt(sum(m.sum_bet_squared * g.payout_multiplier_variance::DOUBLE)) / 100
               / count(*) luck_sd_per_day
           FROM machine_day m JOIN machines mc USING (machine_id) JOIN game_math g
             USING (config_id)
           WHERE m.active AND m.machine_id = 'M-1158' GROUP BY 1""").iloc[0]
    f["m1158_owned"] = float(m.lease_class == "owned")
    f["m1158_theo_per_ah"] = float(m.theo_per_ah)
    f["m1158_loss_per_day"] = float(m.loss_per_day)
    f["m1158_loss_per_day_low"] = float(m.loss_per_day - 1.96 * m.luck_sd_per_day)
    f["m1158_loss_per_day_high"] = float(m.loss_per_day + 1.96 * m.luck_sd_per_day)
    f["m1158_factor"] = 1 - f["floor_comp_cost_per_theo"] - (
        0 if f["m1158_owned"] else REVENUE_SHARE_RATE)
    # Back Forty after the walkway reopened (2025-04-07 onward)
    b = q("""SELECT count(DISTINCT m.gaming_date) d, sum(m.theo_cents)::DOUBLE / 100 theo,
             sum(m.theo_cents) FILTER (WHERE mc.lease_class = 'leased_revenue_share')::DOUBLE
               / sum(m.theo_cents) rs
           FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
           JOIN machines mc USING (machine_id)
           WHERE m.active AND p.zone_id = 'Z-B40' AND m.gaming_date >= DATE '2025-04-07'
           """).iloc[0]
    f["b40_theo_per_day"] = float(b.theo) / float(b.d)
    f["b40_factor"] = 1 - REVENUE_SHARE_RATE * float(b.rs) - f["floor_comp_cost_per_theo"]
    # Downtime and repair by manufacturer (full window, per day)
    d = q("""SELECT mc.manufacturer mf, count(DISTINCT m.machine_id) machines,
             sum(m.scheduled_seconds - m.available_seconds) / 3600.0 / 181 down_h,
             sum(m.scheduled_seconds) / 3600.0 / 181 sched_h,
             sum(m.theo_cents)::DOUBLE / 100 / (sum(m.available_seconds) / 3600.0) theo_per_ah,
             sum(p.repair_cost_usd)::DOUBLE / 181 repair
           FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
           JOIN machines mc USING (machine_id) WHERE m.active GROUP BY 1""").set_index("mf")
    ref = d.loc["Halcyon"]  # lowest-fault manufacturer (Poisson model in Step 1)
    for mf in ["Ridgeline", "Northwind"]:
        r = d.loc[mf]
        key = mf.lower()
        f[f"{key}_machines"] = float(r.machines)
        f[f"{key}_theo_per_ah"] = float(r.theo_per_ah)
        f[f"{key}_excess_down_h_per_day"] = float(r.down_h - r.sched_h * ref.down_h / ref.sched_h)
        f[f"{key}_excess_repair_per_day"] = float(
            r.repair - ref.repair * r.machines / ref.machines)
    f["floor_down_h_per_day"] = float(d.down_h.sum())
    f["floor_theo_per_ah"] = float((d.theo_per_ah * d.sched_h).sum() / d.sched_h.sum())
    # Comp policy change (2025-05-01): comp cost per carded theo before/after
    cp = q("""SELECT gaming_date >= DATE '2025-05-01' post,
               sum(comp_cost_usd) / sum(carded_theo_usd) r FROM contract_comp_day GROUP BY 1
           """) if "contract_comp_day" in repo.list_tables() else q("""
           WITH t AS (SELECT gaming_date, sum(carded_theo_cents)::DOUBLE / 100 ct
                      FROM machine_day GROUP BY 1)
           SELECT p.gaming_date >= DATE '2025-05-01' post,
                  sum(p.comp_cost_usd)::DOUBLE / sum(t.ct) r
           FROM property_day p JOIN t USING (gaming_date) GROUP BY 1""")
    cp = cp.set_index("post").r
    f["comp_cost_per_carded_theo_pre"] = float(cp[False])
    f["comp_cost_per_carded_theo_post"] = float(cp[True])
    # Property promotions: excess theo on Fri-Sun event days vs same-weekday baseline
    f.update(promo_effect(repo))
    return f


def promo_effect(repo: AnalyticsRepository) -> dict[str, float]:
    days = repo.query_df("""
        SELECT p.gaming_date, c.local_weekday wd, p.theo_usd::DOUBLE theo,
               p.events_active
        FROM property_day p JOIN calendar_day c USING (gaming_date) ORDER BY 1""")
    days["gaming_date"] = pd.to_datetime(days.gaming_date)
    ev = repo.query_df("SELECT event_id, start_date, end_date FROM events "
                       "WHERE local_scope = 'property' ORDER BY 1")
    any_event = days.events_active.notna() & (days.events_active != "")
    per_event = []
    for e in ev.itertuples():
        s, t = pd.Timestamp(e.start_date), pd.Timestamp(e.end_date)
        ed = days[(days.gaming_date >= s) & (days.gaming_date <= t)
                  & days.wd.isin(["Fri", "Sat", "Sun"])]
        excess = []
        for r in ed.itertuples():
            base = days[(days.wd == r.wd) & ~any_event
                        & ((days.gaming_date - r.gaming_date).abs() <= pd.Timedelta(days=28))]
            excess.append(r.theo - base.theo.mean())
        per_event.append(float(np.mean(excess)))
    return {"promo_excess_theo_per_day_mean": float(np.mean(per_event)),
            "promo_excess_theo_per_day_low": float(np.min(per_event)),
            "promo_excess_theo_per_day_high": float(np.max(per_event)),
            "promo_events_observed": float(len(per_event))}


def peer_rates(repo: AnalyticsRepository) -> pd.DataFrame:
    return repo.query_df("""
        SELECT p.zone_id, m.config_id, sum(m.theo_cents)::DOUBLE / 100
                 / (sum(m.available_seconds) / 3600.0) rate
        FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
        WHERE m.active AND m.gaming_date >= DATE '2025-04-07' GROUP BY 1, 2""")


def empty_slots(repo: AnalyticsRepository) -> dict[str, int]:
    df = repo.query_df("""
        WITH occ AS (SELECT location_id FROM placements WHERE effective_to_utc IS NULL)
        SELECT f.zone_id, count(*) - count(o.location_id) empty
        FROM floor_locations f LEFT JOIN occ o USING (location_id)
        WHERE f.node_type = 'slot' GROUP BY 1""")
    return {r.zone_id: int(r.empty) for r in df.itertuples()}


# --------------------------------------------------------------------------- build
def build_model(repo: AnalyticsRepository, catalog: ActionCatalog) -> InvestmentModel:
    f = load_facts(repo)
    A = {}

    def add(a: Assumption) -> None:
        A[a.assumption_id] = a

    add(Assumption("A01_inspect_fix_probability",
                   "Probability that inspecting M-1158 finds and corrects the payout fault",
                   0.5, 0.0, 1.0, "probability", ASSUMPTION_REQUIRED,
                   "Not identifiable: catalog says inspection outcome is information only. "
                   "0.5 is an uninformative planning midpoint.",
                   [EV["payout_anomaly"]], "not_identified"))
    add(Assumption("A02_m1158_loss_per_day",
                   "M-1158 house-win shortfall vs theo per active day (systematic part)",
                   f["m1158_loss_per_day"], f["m1158_loss_per_day_low"],
                   f["m1158_loss_per_day_high"], "USD/day", EVIDENCE_ESTIMATE,
                   "machine_day + game_math; range = +/-1.96 luck SD from game-math variance",
                   [EV["payout_anomaly"]], "statistical (hit-rate z=124)"))
    add(Assumption("A03_wayfinding_net_uplift",
                   "Net incremental Back Forty theo from new signage, after cannibalisation",
                   0.025, 0.0, 0.10, "fraction of zone theo", ASSUMPTION_REQUIRED,
                   "Not identifiable: closure shows access matters (-31%), but signage uplift "
                   "is unmeasured. 0-10% exploratory range; 2.5% planning value.",
                   [EV["walkway_closure"]], "not_identified"))
    add(Assumption("A04_preventive_effectiveness",
                   "Share of excess (vs Halcyon) downtime and repair removed by preventive "
                   "maintenance within the horizon",
                   0.5, 0.0, 1.0, "fraction", ASSUMPTION_REQUIRED,
                   "Not identifiable; full range tested. Excess itself is evidence-based.",
                   [EV["downtime"]], "not_identified"))
    add(Assumption("A05_tech_downtime_reduction",
                   "Share of floor downtime removed per added technician",
                   0.15, 0.0, 1.0, "fraction per technician", ASSUMPTION_REQUIRED,
                   "Not identifiable from roster data in this step; full range tested.",
                   [EV["downtime"]], "not_identified"))
    add(Assumption("A06_comp_play_response",
                   "Fraction of carded theo lost if comp points price reverts to pre-May "
                   "levels", 0.01, 0.0, 0.05, "fraction of carded theo", ASSUMPTION_REQUIRED,
                   "Not identifiable: post-change play is confounded by season. 0-5% range.",
                   [EV["comp_change"]], "not_identified"))
    add(Assumption("A07_comp_cost_saving_rate",
                   "Comp cost per carded theo avoided by reverting the points price",
                   f["comp_cost_per_carded_theo_post"] - f["comp_cost_per_carded_theo_pre"],
                   0.0, f["comp_cost_per_carded_theo_post"] - f["comp_cost_per_carded_theo_pre"],
                   "USD per USD carded theo", EVIDENCE_ESTIMATE,
                   "contract_comp_day pre/post 2025-05-01; associational (before/after)",
                   [EV["comp_change"]], "associational"))
    add(Assumption("A08_promo_excess_theo_per_day",
                   "Excess floor theo per Fri-Sun promotion day vs same-weekday baseline",
                   f["promo_excess_theo_per_day_mean"], f["promo_excess_theo_per_day_low"],
                   f["promo_excess_theo_per_day_high"], "USD/day", EVIDENCE_ESTIMATE,
                   f"property_day; {int(f['promo_events_observed'])} past property promotions "
                   "(range = min/max across events); baseline = same weekday within 28 days, "
                   "no events", [], "associational"))
    add(Assumption("A09_move_location_transfer",
                   "Share of the destination-zone same-config demand gap a moved machine "
                   "captures", 0.5, 0.0, 1.0, "fraction", ASSUMPTION_REQUIRED,
                   "Location effect is strong and persistent (rank correlation 0.987), but "
                   "transfer to a new slot is unmeasured; full range tested.",
                   [EV["decomposition"], EV["persistence"]], "not_identified"))

    add(Assumption("A10_replacement_gap_capture",
                   "Share of the gap to the best observed title rate that a new title "
                   "achieves in the replaced slot", 0.5, 0.0, 1.0, "fraction",
                   ASSUMPTION_REQUIRED,
                   "New-title performance is unmeasured; 1.0 = the best title ever observed "
                   "in this zone (evidence ceiling).", [EV["decomposition"]], "not_identified"))

    cands: list[Candidate] = []
    cands.append(Candidate(
        "INV-INSPECT-M1158", "A-INSPECT", "M-1158", 1, True, "payout anomaly evidence",
        ["A01_inspect_fix_probability", "A02_m1158_loss_per_day"],
        "Hit rate 38.6% vs 31.5% configured; ~$200/day shortfall", ASSUMPTION_REQUIRED,
        "statistical anomaly; fix effect not identified", [EV["payout_anomaly"]]))
    cands.append(Candidate(
        "INV-WAYFIND-B40", "A-WAYFINDING", "Z-B40", 1, True,
        "only zone with access evidence (walkway closure)", ["A03_wayfinding_net_uplift"],
        "Zone demand fell 31% when access was cut", ASSUMPTION_REQUIRED,
        "uplift not identified", [EV["walkway_closure"]],
        notes="Other zones: no access evidence -> not candidates"))
    for mf in ["Ridgeline", "Northwind"]:
        cands.append(Candidate(
            f"INV-PREVENT-{mf.upper()}", "A-PREVENTIVE", mf, 1, True,
            f"{mf} fault rate above Halcyon (Poisson, age-adjusted)",
            ["A04_preventive_effectiveness"],
            f"{mf} excess downtime {f[mf.lower() + '_excess_down_h_per_day']:.2f} h/day",
            ASSUMPTION_REQUIRED, "effect not identified; ceiling evidence-based",
            [EV["downtime"]]))
    cands.append(Candidate(
        "INV-TECH-SHIFT", "A-TECH-SHIFT", "floor", 3, True, "floor downtime",
        ["A05_tech_downtime_reduction"],
        f"Floor downtime {f['floor_down_h_per_day']:.1f} h/day", ASSUMPTION_REQUIRED,
        "effect not identified; ceiling evidence-based", [EV["downtime"]]))
    cands.append(Candidate(
        "INV-COMP-REVERT", "A-COMP-CHANGE", "property", 1, True,
        "points price halved 2025-05-01",
        ["A06_comp_play_response", "A07_comp_cost_saving_rate"],
        "Comp cost per carded theo rose after the change", ASSUMPTION_REQUIRED,
        "associational saving; play response not identified", [EV["comp_change"]]))
    cands.append(Candidate(
        "INV-COMP-PILOT", "A-COMP-PILOT", "property", 1, True,
        "information value only", [], "Measures comp response; no financial uplift in horizon",
        NOT_IDENTIFIABLE, "value of information, not modelled", [EV["comp_change"]],
        notes="Excluded from the financial objective (not treated as zero)"))
    cands.append(Candidate(
        "INV-PROMO", "A-PROMO", "property weekend", 2, True, "past property promotions",
        ["A08_promo_excess_theo_per_day"], "Excess theo on past promotion weekends",
        EVIDENCE_ESTIMATE, "associational (2 past events)", []))
    # Moves: Back Forty machines into empty slots of higher-demand zones (same config peers)
    caps = empty_slots(repo)
    pr = peer_rates(repo)
    rate = {(r.zone_id, r.config_id): r.rate for r in pr.itertuples()}
    b40 = repo.query_df("""
        SELECT m.machine_id, any_value(m.config_id) config_id,
               sum(m.theo_cents)::DOUBLE / 100 / (sum(m.available_seconds) / 3600.0) own
        FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
        WHERE m.active AND p.zone_id = 'Z-B40' AND m.gaming_date >= DATE '2025-04-07'
        GROUP BY 1""")
    move_opts = []
    for zone in sorted(z for z in caps if caps[z] > 0 and z != "Z-B40"):
        for r in b40.itertuples():
            if r.machine_id == "M-1158":
                continue  # interaction with the inspection is not modelled -> excluded
            dest = rate.get((zone, r.config_id))
            if dest is None:
                continue
            move_opts.append((dest - r.own, zone, r.machine_id, r.config_id, dest, r.own))
    move_opts.sort(key=lambda x: (-x[0], x[1], x[2]))
    movers = move_opts[:6]
    # No double counting: wayfinding uplift applies only to Back Forty demand that stays
    # in Back Forty, so every move candidate's own demand is removed from its base.
    f["b40_theo_per_day_excl_movers"] = f["b40_theo_per_day"] - sum(
        own * 24 for _, _, mid, _, _, own in {(0, 0, x[2], 0, 0, x[5]) for x in movers})
    for gap, zone, mid, cfg, dest, own in movers:
        f[f"move_gap_{mid}_{zone}"] = float(gap)
        cands.append(Candidate(
            f"INV-MOVE-{mid}-{zone}", "A-MOVE-MACHINE", f"{mid}->{zone}", 1, True,
            f"empty slot in {zone}; same config {cfg} observed there",
            ["A09_move_location_transfer"],
            f"{cfg}: {own:.2f} $/h now vs {dest:.2f} $/h in {zone}", ASSUMPTION_REQUIRED,
            "location transfer not identified", [EV["decomposition"], EV["persistence"]],
            machines=[mid], capacity_group=zone))
    # Replacements: ceiling = best observed same-zone config rate, or the newest title
    # scaled by the zone ratio, whichever is higher (EVIDENCE_UPPER_BOUND)
    zr = repo.query_df("""SELECT p.zone_id, sum(m.theo_cents)::DOUBLE / 100
                            / (sum(m.available_seconds) / 3600.0) r
                          FROM machine_day m JOIN prepared_daily_view p
                            USING (machine_id, gaming_date)
                          WHERE m.active GROUP BY 1""").set_index("zone_id").r
    newest = max(v for (z, cfg), v in rate.items() if cfg == "G-NEW91")
    newest_ratio = zr["Z-B40"] / zr["Z-PIT"]
    ceiling = max(max(v for (z, _), v in rate.items() if z == "Z-B40"), newest * newest_ratio)
    worst = b40.sort_values(["own", "machine_id"]).iloc[0]
    f["replace_ceiling_rate"] = float(ceiling)
    f["replace_target_rate"] = float(worst.own)
    for act in ["A-REPLACE-LEASE", "A-REPLACE-BUY"]:
        cands.append(Candidate(
            f"INV-{act.removeprefix('A-')}-{worst.machine_id}", act, str(worst.machine_id), 1,
            True, "lowest-demand Back Forty machine", ["A10_replacement_gap_capture"],
            f"{worst.machine_id} {worst.own:.2f} $/h; ceiling {ceiling:.2f} $/h",
            ASSUMPTION_REQUIRED, "title effect not identified; ceiling evidence-based",
            [EV["decomposition"]], machines=[str(worst.machine_id)],
            notes="Benefit evaluated at the ceiling: if negative there, excluded robustly"))
    cands.append(Candidate("INV-SURVEY", "A-SURVEY", "property", 1, True,
                           "information value only", [], "Triples survey sample",
                           NOT_IDENTIFIABLE, "value of information, not modelled", []))
    cands.append(Candidate("INV-MOVE-BANK", "A-MOVE-BANK", "-", 3, False,
                           "no empty bank-sized destination capacity on the floor", [],
                           "-", NOT_IDENTIFIABLE, "-", []))
    return InvestmentModel(f, A, cands, catalog, caps)


# --------------------------------------------------------------------------- economics
@dataclass
class Economics:
    candidate_id: str
    unit_cost: float
    effective_days: int
    max_quantity: int
    gross_theo_gain: float  # per unit
    contribution_gain: float
    avoided_costs: float
    downtime_cost: float
    net_per_unit: float | None  # None = not admissible / not identifiable
    status: str
    blocked_by: list[str]


def unit_cost_usd(model: InvestmentModel, action: str) -> float:
    a = model.catalog.actions[action]
    days = effective_days(a.lead_days, model.lead_delay_days)
    return model.cost_multiplier * (a.unit_cost_cents + a.recurring_cost_cents_per_day * days
                                    ) / 100


def economics(model: InvestmentModel, c: Candidate) -> Economics:
    f, a = model.facts, model.a
    act = model.catalog.actions[c.action_type]
    days = effective_days(act.lead_days, model.lead_delay_days)
    cost = unit_cost_usd(model, c.action_type)
    blocked = [k for k in c.assumptions if not model.assumptions[k].valid]
    dm, fl = model.demand_multiplier, f["floor_contribution_factor"]
    gross = contrib = avoided = down = 0.0
    qty = c.max_quantity
    if c.benefit_status == NOT_IDENTIFIABLE or not c.eligible:
        return Economics(c.candidate_id, cost, days, qty, 0, 0, 0, 0, None,
                         NOT_IDENTIFIABLE if c.eligible else "INELIGIBLE", blocked)
    if c.action_type == "A-INSPECT":
        gross = a("A01_inspect_fix_probability") * a("A02_m1158_loss_per_day") * dm * max(
            0, days - 1)  # fix applies after the inspection day
        contrib = gross * f["m1158_factor"]
        down = act.downtime_minutes / 60 * f["m1158_theo_per_ah"] * dm * f["m1158_factor"]
    elif c.action_type == "A-WAYFINDING":
        base = f.get("b40_theo_per_day_excl_movers", f["b40_theo_per_day"]) * (
            model.b40_multiplier * dm)
        gross = a("A03_wayfinding_net_uplift") * base * days
        contrib = gross * f["b40_factor"]
    elif c.action_type == "A-PREVENTIVE":
        k = c.target_entity.lower()
        e = a("A04_preventive_effectiveness")
        gross = e * f[f"{k}_excess_down_h_per_day"] * f[f"{k}_theo_per_ah"] * dm * days
        contrib = gross * fl
        avoided = e * f[f"{k}_excess_repair_per_day"] * days
        down = act.downtime_minutes / 60 * f[f"{k}_machines"] * f[f"{k}_theo_per_ah"] * dm * fl
    elif c.action_type == "A-TECH-SHIFT":
        gross = a("A05_tech_downtime_reduction") * f["floor_down_h_per_day"] * f[
            "floor_theo_per_ah"] * dm * days
        contrib = gross * fl
    elif c.action_type == "A-COMP-CHANGE":
        ct = f["carded_theo_per_day"] * dm
        avoided = a("A07_comp_cost_saving_rate") * ct * days
        contrib = -a("A06_comp_play_response") * ct * days * fl
        gross = -a("A06_comp_play_response") * ct * days
    elif c.action_type == "A-PROMO":
        gross = a("A08_promo_excess_theo_per_day") * dm * 3  # Fri-Sun
        contrib = gross * fl  # comp cost of extra play is inside the factor
        qty = min(c.max_quantity, promo_weekends(act.lead_days, model.lead_delay_days))
    elif c.action_type == "A-MOVE-MACHINE":
        mid, zone = c.target_entity.split("->")
        gap = f[f"move_gap_{mid}_{zone}"]
        gross = a("A09_move_location_transfer") * gap * 24 * days * dm
        contrib = gross * fl
        down = act.downtime_minutes / 60 * f["replace_target_rate"] * dm * fl
    elif c.action_type in ("A-REPLACE-LEASE", "A-REPLACE-BUY"):
        gain = a("A10_replacement_gap_capture") * (
            f["replace_ceiling_rate"] - f["replace_target_rate"]) * 24 * days * dm
        gross, contrib = gain, gain * fl
        down = act.downtime_minutes / 60 * f["replace_target_rate"] * dm * fl
    net = contrib + avoided - down - cost
    status = c.benefit_status
    if status == ASSUMPTION_REQUIRED and _best_case_net(model, c) <= 0:
        status = NEGATIVE_AT_BEST_CASE  # loses money at every tested assumption value
    if blocked:
        status = "BLOCKED"
    if days == 0 or qty == 0:
        qty = 0
    return Economics(c.candidate_id, cost, days, qty, gross, contrib, avoided, down,
                     None if blocked else net, status, blocked)


def _best_case_net(model: InvestmentModel, c: Candidate) -> float:
    """Max net over all low/high combinations of the candidate's assumption ranges."""
    import itertools
    keys = [k for k in c.assumptions if model.assumptions[k].valid]
    best = -float("inf")
    for combo in itertools.product(*[(model.assumptions[k].low, model.assumptions[k].high)
                                     for k in keys]):
        m = model
        for k, v in zip(keys, combo, strict=True):
            m = m.with_assumption(k, v)
        cc = copy.copy(c)
        cc.benefit_status = EVIDENCE_ESTIMATE  # avoid recursion into this check
        e = economics(m, cc)
        if e.net_per_unit is not None:
            best = max(best, e.net_per_unit)
    return best
