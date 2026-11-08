"""Validated representation of the official action catalog and a cost validator.

Prices a hypothetical selection of actions; it does not optimise a portfolio.
Budget rule (GUIDE.md section 6), in cents:
    cost = quantity x (unit_cost_cents + recurring_cost_cents_per_day x max(0, H - lead_days))
with H = 30-day horizon starting 2025-07-01. Fixed packages are charged in full.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field, model_validator

from backend.repositories.base import AnalyticsRepository

BUDGET_CENTS = 10_000_000  # $100,000
HORIZON_START = date(2025, 7, 1)
HORIZON_DAYS = 30
MAX_ACTION_TYPES = 3
HOLD_ACTION = "A-HOLD"
EXPECTED_ACTIONS = 13

# Eligible target kind per catalog unit (from the `unit` column).
TARGET_KIND = {
    "machine": "machine_id", "bank": "bank_id", "technician_shift": "shift",
    "manufacturer": "manufacturer", "zone": "zone_id", "pilot": "property",
    "policy": "property", "event": "weekend", "month": "month", "none": "none",
}


class CatalogAction(BaseModel):
    action_type_id: str
    name: str
    unit: str
    unit_cost_cents: int = Field(ge=0)
    recurring_cost_cents_per_day: int = Field(ge=0)
    lead_days: int = Field(ge=0)
    downtime_minutes: int = Field(ge=0)
    quantity_limit: int = Field(ge=1)
    incompatibility_group: str | None = None
    notes: str | None = None

    @property
    def eligible_target(self) -> str:
        return TARGET_KIND.get(self.unit, self.unit)

    @property
    def operating_days(self) -> int:
        return max(0, HORIZON_DAYS - self.lead_days)

    @property
    def effective_from(self) -> date:
        return HORIZON_START + timedelta(days=self.lead_days)

    @property
    def effective_to(self) -> date:
        return HORIZON_START + timedelta(days=HORIZON_DAYS - 1)

    def unit_cost_in_horizon_cents(self) -> int:
        return self.unit_cost_cents + self.recurring_cost_cents_per_day * self.operating_days

    def cost_formula(self) -> str:
        if self.recurring_cost_cents_per_day:
            return (f"qty x (${self.unit_cost_cents / 100:,.2f} + "
                    f"${self.recurring_cost_cents_per_day / 100:,.2f}/day x "
                    f"{self.operating_days} days)")
        return f"qty x ${self.unit_cost_cents / 100:,.2f}"

    def summary(self) -> dict[str, object]:
        return {
            **self.model_dump(),
            "eligible_target": self.eligible_target,
            "cost_formula": self.cost_formula(),
            "unit_cost_in_horizon_usd": self.unit_cost_in_horizon_cents() / 100,
            "effective_operating_period": f"{self.effective_from} to {self.effective_to} "
                                          f"({self.operating_days} days)",
            "physical_constraint": (f"{self.downtime_minutes} min machine downtime per unit"
                                    if self.downtime_minutes else "no machine downtime"),
        }


class ActionCatalog(BaseModel):
    actions: dict[str, CatalogAction]

    @model_validator(mode="after")
    def _check(self) -> ActionCatalog:
        if len(self.actions) != EXPECTED_ACTIONS:
            raise ValueError(f"expected {EXPECTED_ACTIONS} actions, got {len(self.actions)}")
        if HOLD_ACTION not in self.actions:
            raise ValueError("catalog lacks the budget-hold action")
        return self

    @classmethod
    def load(cls, repo: AnalyticsRepository) -> ActionCatalog:
        df = repo.query_df("SELECT * FROM action_catalog ORDER BY action_type_id")
        rows = [CatalogAction.model_validate(
            {k: (None if (isinstance(v, float) and v != v) else v) for k, v in r.items()})
            for r in df.to_dict("records")]
        return cls(actions={a.action_type_id: a for a in rows})


class SelectedAction(BaseModel):
    action_type_id: str
    quantity: int = Field(ge=1)
    targets: list[str] = Field(default_factory=list)
    extra_cost_cents: int = Field(0, ge=0, description="e.g. proposed added comp spend")


class PricedLine(BaseModel):
    action_type_id: str
    quantity: int
    unit_cost_in_horizon_cents: int
    extra_cost_cents: int
    total_cents: int
    operating_days: int
    downtime_minutes_total: int


class PricingResult(BaseModel):
    lines: list[PricedLine]
    total_cents: int
    budget_cents: int = BUDGET_CENTS
    unspent_cents: int
    action_types_used: int
    valid: bool
    violations: list[str]

    @property
    def total_usd(self) -> float:
        return self.total_cents / 100


def price_selection(catalog: ActionCatalog, selection: list[SelectedAction]) -> PricingResult:
    """Price a hypothetical selection and list every rule it breaks."""
    violations: list[str] = []
    lines: list[PricedLine] = []
    seen: dict[str, int] = {}
    target_groups: dict[tuple[str, str], str] = {}

    for sel in selection:
        a = catalog.actions.get(sel.action_type_id)
        if a is None:
            violations.append(f"{sel.action_type_id}: not in the official catalog")
            continue
        seen[a.action_type_id] = seen.get(a.action_type_id, 0) + sel.quantity
        if sel.targets and len(sel.targets) != sel.quantity:
            violations.append(f"{a.action_type_id}: {len(sel.targets)} targets for quantity "
                              f"{sel.quantity}")
        if len(set(sel.targets)) != len(sel.targets):
            violations.append(f"{a.action_type_id}: duplicate targets")
        if a.incompatibility_group == "same_machine":
            for t in sel.targets:
                prev = target_groups.get(("same_machine", t))
                if prev and prev != a.action_type_id:
                    violations.append(f"{t}: {prev} conflicts with {a.action_type_id} "
                                      "(same_machine group)")
                target_groups[("same_machine", t)] = a.action_type_id
        unit = a.unit_cost_in_horizon_cents()
        lines.append(PricedLine(
            action_type_id=a.action_type_id, quantity=sel.quantity,
            unit_cost_in_horizon_cents=unit, extra_cost_cents=sel.extra_cost_cents,
            total_cents=sel.quantity * unit + sel.extra_cost_cents,
            operating_days=a.operating_days,
            downtime_minutes_total=sel.quantity * a.downtime_minutes))

    for aid, qty in seen.items():
        a = catalog.actions[aid]
        if qty > a.quantity_limit:
            violations.append(f"{aid}: quantity {qty} exceeds limit {a.quantity_limit}")
        if a.operating_days == 0 and aid != HOLD_ACTION:
            violations.append(f"{aid}: lead time leaves no operating days in the horizon")

    groups: dict[str, list[str]] = {}
    for aid in seen:
        g = catalog.actions[aid].incompatibility_group
        if g and g != "same_machine":
            groups.setdefault(g, []).append(aid)
    for g, ids in groups.items():
        if len(ids) > 1:
            violations.append(f"incompatible actions in group '{g}': {sorted(ids)}")

    funded = [a for a in seen if a != HOLD_ACTION]
    if len(funded) > MAX_ACTION_TYPES:
        violations.append(f"{len(funded)} action types funded; maximum is {MAX_ACTION_TYPES}")

    total = sum(line.total_cents for line in lines)
    if total > BUDGET_CENTS:
        violations.append(f"total ${total / 100:,.2f} exceeds budget "
                          f"${BUDGET_CENTS / 100:,.2f}")
    return PricingResult(lines=lines, total_cents=total, unspent_cents=BUDGET_CENTS - total,
                         action_types_used=len(funded), valid=not violations,
                         violations=violations)
