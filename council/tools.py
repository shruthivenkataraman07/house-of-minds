"""Read-only, allowlisted evidence tools for council agents.

Agents can only call the named tools below. Each tool runs a fixed, parameterised query
over verified tables, validates entity IDs against a strict pattern AND against the data,
and returns a ToolResult (value, unit, query reference, source tables, evidence IDs).
No agent text is ever executed as SQL. Tools never write.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backend.repositories.base import AnalyticsRepository
from optimization.investment_model import EV, InvestmentModel

ID_PATTERNS = {"machine_id": r"^M-\d{4}$", "zone_id": r"^Z-[A-Z0-9]{2,4}$",
               "manufacturer": r"^[A-Z][a-z]+$", "event_id": r"^EV-P-[A-Z]+$"}


class ToolError(ValueError):
    pass


@dataclass(frozen=True)
class ToolResult:
    tool: str
    params: tuple[tuple[str, str], ...]
    value: float
    unit: str
    source_tables: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    @property
    def query_ref(self) -> str:
        key = f"{self.tool}|{self.params}"
        return "Q-" + hashlib.sha256(key.encode()).hexdigest()[:10].upper()


class EvidenceTools:
    def __init__(self, repo: AnalyticsRepository, model: InvestmentModel) -> None:
        self._repo = repo
        self._model = model
        self.calls: list[str] = []

    # ---------------------------------------------------------------- guards
    def _validate(self, kind: str, value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(ID_PATTERNS[kind], value):
            raise ToolError(f"invalid {kind}: {value!r}")
        return value

    def call(self, name: str, **params: str) -> ToolResult:
        """Single entry point: only allowlisted tools; parameters validated."""
        if name not in ALLOWLIST:
            raise ToolError(f"tool not allowed: {name!r}")
        self.calls.append(name)
        return ALLOWLIST[name](self, **params)

    # ---------------------------------------------------------------- tools
    def promo_event_excess(self) -> ToolResult:
        f = self._model.facts
        return ToolResult("promo_event_excess", (), f["promo_excess_theo_per_day_low"],
                          "USD/day", ("property_day", "calendar_day", "events"), (),
                          {"low": f["promo_excess_theo_per_day_low"],
                           "high": f["promo_excess_theo_per_day_high"],
                           "mean": f["promo_excess_theo_per_day_mean"],
                           "events": int(f["promo_events_observed"])})

    def weekend_noise_sd(self) -> ToolResult:
        """SD of Fri-Sun floor theo around same-weekday 28-day means on non-event days."""
        d = self._repo.query_df("""
            SELECT p.gaming_date, c.local_weekday wd, p.theo_usd::DOUBLE theo, p.events_active
            FROM property_day p JOIN calendar_day c USING (gaming_date) ORDER BY 1""")
        d["gaming_date"] = pd.to_datetime(d.gaming_date)
        clean = d[(d.events_active.isna() | (d.events_active == ""))]
        res = []
        for r in clean[clean.wd.isin(["Fri", "Sat", "Sun"])].itertuples():
            base = clean[(clean.wd == r.wd) & (clean.gaming_date != r.gaming_date)
                         & ((clean.gaming_date - r.gaming_date).abs()
                            <= pd.Timedelta(days=28))]
            if len(base) >= 3:
                res.append(r.theo - base.theo.mean())
        return ToolResult("weekend_noise_sd", (), float(np.std(res, ddof=1)), "USD/day",
                          ("property_day", "calendar_day"), (), {"n_days": len(res)})

    def post_event_carded_change(self) -> ToolResult:
        """Carded theo/day in the 7 days after each property promotion vs same weekdays
        3-4 weeks earlier (displacement check). Tracked play only."""
        ev = self._repo.query_df("SELECT event_id, start_date, end_date FROM events "
                                 "WHERE local_scope = 'property' ORDER BY 1")
        d = self._repo.query_df("""SELECT gaming_date, sum(carded_theo_cents)::DOUBLE / 100 ct
                                   FROM machine_day GROUP BY 1 ORDER BY 1""")
        d["gaming_date"] = pd.to_datetime(d.gaming_date)
        s = d.set_index("gaming_date").ct
        per = {}
        for e in ev.itertuples():
            end = pd.Timestamp(e.end_date)
            after = [end + pd.Timedelta(days=k) for k in range(1, 8)]
            before = [x - pd.Timedelta(days=w) for x in after for w in (21, 28)]
            a = s.reindex(after).dropna()
            b = s.reindex(before).dropna()
            if len(a) == 7 and len(b) >= 10:
                per[e.event_id] = float(a.mean() / b.mean() - 1)
        val = float(np.mean(list(per.values()))) if per else float("nan")
        return ToolResult("post_event_carded_change", (), val, "fraction",
                          ("events", "machine_day"), (), {"per_event": per})

    def promo_comp_ratio(self) -> ToolResult:
        """Comp cost per theo on property-promotion days vs all other days."""
        r = self._repo.query_df("""
            WITH ev AS (SELECT c.gaming_date, count(e.event_id) > 0 promo
                        FROM calendar_day c LEFT JOIN events e
                          ON c.gaming_date BETWEEN e.start_date AND e.end_date
                         AND e.local_scope = 'property' GROUP BY 1)
            SELECT ev.promo, sum(p.comp_cost_usd)::DOUBLE / sum(p.theo_usd) r, count(*) n
            FROM property_day p JOIN ev USING (gaming_date) GROUP BY 1""").set_index("promo")
        return ToolResult("promo_comp_ratio", (), float(r.loc[True, "r"]), "USD per USD theo",
                          ("property_day", "events", "calendar_day"), (EV["comp_change"],),
                          {"promo_days": int(r.loc[True, "n"]), "other": float(r.loc[False, "r"]),
                           "promo": float(r.loc[True, "r"])})

    def comp_change_date(self) -> ToolResult:
        """Change-point gaming date of the comp points price (Step 2 investigation)."""
        d = self._repo.query_df("""
            SELECT c.gaming_date, -sum(l.points_delta)::DOUBLE / (sum(l.face_value_cents) / 100.0) r
            FROM loyalty_ledger l JOIN calendar_day c
              ON l.event_at_utc >= c.gaming_day_start_utc AND l.event_at_utc < c.gaming_day_end_utc
            WHERE l.event_type = 'redeem' GROUP BY 1 ORDER BY 1""")
        best, split = -1.0, None
        for i in range(14, len(d) - 14):
            a, b = d.r.iloc[:i], d.r.iloc[i:]
            sc = (a.mean() - b.mean()) ** 2 * i * (len(d) - i)
            if sc > best:
                best, split = sc, d.gaming_date.iloc[i]
        first_promo = self._repo.scalar("SELECT min(start_date) FROM events "
                                        "WHERE local_scope = 'property' "
                                        "AND start_date >= DATE '2025-04-01'")
        ts = pd.Timestamp(split)
        return ToolResult("comp_change_date", (), float(ts.toordinal()), "ordinal date",
                          ("loyalty_ledger", "calendar_day", "events"), (EV["comp_change"],),
                          {"change_date": str(ts.date()),
                           "next_property_promo_start": str(pd.Timestamp(first_promo).date())})

    def zone_occupancy(self, zone_id: str) -> ToolResult:
        z = self._validate("zone_id", zone_id)
        r = self._repo.query_df("""
            SELECT sum(m.occupied_seconds)::DOUBLE / sum(m.available_seconds) occ,
                   count(DISTINCT m.machine_id) machines
            FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
            WHERE m.active AND p.zone_id = $zone AND m.gaming_date >= DATE '2025-04-07'""",
            {"zone": z}).iloc[0]
        if int(r.machines) == 0:
            raise ToolError(f"unknown zone {z}")
        return ToolResult("zone_occupancy", (("zone_id", z),), float(r.occ), "fraction",
                          ("machine_day", "prepared_daily_view"), (EV["decomposition"],),
                          {"machines": int(r.machines)})

    def zone_count_elasticity(self, zone_id: str) -> ToolResult:
        """Slope of zone daily theo on its active machine count, relative to the mean
        theo per machine. ~1 = extra machines add demand; ~0 = they redistribute it."""
        z = self._validate("zone_id", zone_id)
        d = self._repo.query_df("""
            SELECT m.gaming_date, count(*) n, sum(m.theo_cents)::DOUBLE / 100 theo
            FROM machine_day m JOIN prepared_daily_view p USING (machine_id, gaming_date)
            WHERE m.active AND p.zone_id = $zone GROUP BY 1""", {"zone": z})
        if d.n.nunique() < 3:
            return ToolResult("zone_count_elasticity", (("zone_id", z),), float("nan"),
                              "ratio", ("machine_day", "prepared_daily_view"), (),
                              {"distinct_counts": int(d.n.nunique()), "identifiable": False})
        d["gaming_date"] = pd.to_datetime(d.gaming_date)
        d["dow"] = d.gaming_date.dt.day_of_week
        x = d.n - d.groupby("dow").n.transform("mean")
        y = d.theo - d.groupby("dow").theo.transform("mean")
        slope = float((x * y).sum() / (x * x).sum()) if (x * x).sum() > 0 else float("nan")
        per_machine = float(d.theo.sum() / d.n.sum())
        return ToolResult("zone_count_elasticity", (("zone_id", z),), slope / per_machine,
                          "ratio", ("machine_day", "prepared_daily_view"), (),
                          {"distinct_counts": int(d.n.nunique()), "identifiable": True,
                           "slope_usd_per_machine_day": slope, "mean_usd_per_machine": per_machine,
                           "count_range": [int(d.n.min()), int(d.n.max())]})

    def machine_monthly_hit_z(self, machine_id: str) -> ToolResult:
        mid = self._validate("machine_id", machine_id)
        d = self._repo.query_df("""
            SELECT substr(CAST(m.gaming_date AS STRING), 1, 7) mon, sum(m.paid_spins) n,
                   sum(m.payout_positive_spins) h, any_value(g.hit_probability)::DOUBLE p
            FROM machine_day m JOIN game_math g USING (config_id)
            WHERE m.active AND m.machine_id = $mid GROUP BY 1 ORDER BY 1""", {"mid": mid})
        if d.empty:
            raise ToolError(f"unknown machine {mid}")
        z = (d.h - d.n * d.p) / np.sqrt(d.n * d.p * (1 - d.p))
        return ToolResult("machine_monthly_hit_z", (("machine_id", mid),), float(z.min()),
                          "z (minimum monthly)", ("machine_day", "game_math"),
                          (EV["payout_anomaly"],),
                          {"months": len(d), "months_z_gt_3": int((z > 3).sum())})

    def tech_staffing(self) -> ToolResult:
        r = self._repo.query_df("""
            SELECT sum(actual_headcount)::DOUBLE / sum(planned_headcount) fill,
                   count(*) FILTER (WHERE actual_headcount < planned_headcount) short_shifts,
                   count(*) shifts
            FROM shift_roster WHERE role = 'slot_tech'""").iloc[0]
        return ToolResult("tech_staffing", (), float(r.fill), "actual/planned",
                          ("shift_roster",), (),
                          {"short_shifts": int(r.short_shifts), "shifts": int(r.shifts)})

    def maintenance_fault_effect(self, manufacturer: str) -> ToolResult:
        """Faults per machine-day 60 days before vs after scheduled maintenance on machines
        that received it (the only observed maintenance events)."""
        self._validate("manufacturer", manufacturer)
        d = self._repo.query_df("""
            WITH mt AS (SELECT o.machine_id, o.opened_at_utc t FROM operations o
                        WHERE o.event_type = 'scheduled_maintenance')
            SELECT mt.machine_id, mc.manufacturer,
              count(f.operation_id) FILTER (WHERE f.opened_at_utc < mt.t
                    AND f.opened_at_utc >= mt.t - INTERVAL 60 DAY) before_n,
              count(f.operation_id) FILTER (WHERE f.opened_at_utc > mt.t
                    AND f.opened_at_utc <= mt.t + INTERVAL 60 DAY) after_n
            FROM mt JOIN machines mc USING (machine_id)
            LEFT JOIN operations f ON f.machine_id = mt.machine_id
                 AND f.event_type = 'fault_repair'
            GROUP BY 1, 2""")
        sub = d[d.manufacturer == manufacturer]
        return ToolResult("maintenance_fault_effect", (("manufacturer", manufacturer),),
                          float(len(sub)), "maintained machines",
                          ("operations", "machines"), (EV["downtime"],),
                          {"all_maintained": len(d), "before": int(d.before_n.sum()),
                           "after": int(d.after_n.sum()),
                           "this_manufacturer": len(sub)})

    def portfolio_comparison(self) -> ToolResult:
        """Step 3 baseline portfolios (re-optimised with the canonical model, read-only)."""
        from optimization.portfolio import MODE_CONDITIONAL, MODE_EVIDENCE, optimise
        e = optimise(self._model, MODE_EVIDENCE)
        c = optimise(self._model, MODE_CONDITIONAL)
        return ToolResult("portfolio_comparison", (), c.net_benefit - e.net_benefit, "USD",
                          ("optimization_runs", "portfolio_allocations"), (),
                          {"evidence": [e.signature, e.total_cost, e.net_benefit],
                           "conditional": [c.signature, c.total_cost, c.net_benefit],
                           "extra_cost": c.total_cost - e.total_cost})

    def reoptimise_with(self, assumption_id: str, value: str) -> ToolResult:
        """Read-only what-if on the canonical model; returns portfolio signatures."""
        from optimization.portfolio import MODE_CONDITIONAL, MODE_EVIDENCE, optimise
        if assumption_id not in self._model.assumptions:
            raise ToolError(f"unknown assumption {assumption_id!r}")
        v = float(value)
        m = self._model.with_assumption(assumption_id, v)
        e, c = optimise(m, MODE_EVIDENCE), optimise(m, MODE_CONDITIONAL)
        base_e = optimise(self._model, MODE_EVIDENCE)
        return ToolResult("reoptimise_with", (("assumption_id", assumption_id),
                                              ("value", value)),
                          e.net_benefit - base_e.net_benefit, "USD",
                          ("intervention_assumptions", "investment_candidates"), (),
                          {"evidence": e.signature, "conditional": c.signature,
                           "evidence_base": base_e.signature})


ALLOWLIST: dict[str, Callable[..., ToolResult]] = {
    "promo_event_excess": EvidenceTools.promo_event_excess,
    "weekend_noise_sd": EvidenceTools.weekend_noise_sd,
    "post_event_carded_change": EvidenceTools.post_event_carded_change,
    "promo_comp_ratio": EvidenceTools.promo_comp_ratio,
    "comp_change_date": EvidenceTools.comp_change_date,
    "zone_occupancy": EvidenceTools.zone_occupancy,
    "zone_count_elasticity": EvidenceTools.zone_count_elasticity,
    "machine_monthly_hit_z": EvidenceTools.machine_monthly_hit_z,
    "tech_staffing": EvidenceTools.tech_staffing,
    "maintenance_fault_effect": EvidenceTools.maintenance_fault_effect,
    "portfolio_comparison": EvidenceTools.portfolio_comparison,
    "reoptimise_with": EvidenceTools.reoptimise_with,
}
