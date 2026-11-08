"""Pydantic models for the dashboard API (v1). Every response carries `meta`."""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")
Record = dict[str, Any]


class Meta(BaseModel):
    snapshot_id: str
    data_mode: Literal["snapshot", "databricks"]
    served_from: Literal["snapshot", "databricks", "mixed"]
    exported_at_utc: str
    official_window: str = "2025-01-01..2025-06-30"
    decision_horizon: str = "2025-07-01..2025-07-30"
    period: str | None = None
    units: str = "USD unless stated; modeled values are contribution, not realized profit"
    sources: list[str]


class Envelope(BaseModel, Generic[T]):  # noqa: UP046 (pydantic generic model)
    meta: Meta
    data: T


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    data_mode: str
    snapshot_id: str
    live_error: str | None = None


class Metadata(BaseModel):
    snapshot_id: str
    exported_at_utc: str
    sidecar_snapshot_id: str
    sidecar_exported_at_utc: str
    verified_files: int
    data_mode: str
    live: bool
    note: str


class Verdict(BaseModel):
    model_config = ConfigDict(extra="allow")
    answer: str
    question: str
    machines_reviewed: int
    replacement_justified: int
    retired_already: int
    inspect_instead: int
    not_economic: int
    insufficient_evidence: int
    council_agreement: int
    recommended_option: str
    recommended_allocation: str
    recommended_cost_usd: float
    recommended_net_usd: float


class Portfolio(BaseModel):
    model_config = ConfigDict(extra="allow")
    option: str
    allocation: str
    action_types: int
    cost_usd: float
    remaining_budget_usd: float
    expected_incremental_contribution_usd: float | None
    expected_net_benefit_usd: float | None
    net_low_usd: float | None
    net_high_usd: float | None
    uncertainty_basis: str
    feasible: bool
    note: str
    horizon: str


class BottomMachine(BaseModel):
    machine_id: str
    manager_rank: int
    house_win_usd: float
    verdict: str
    council_verdict: str
    lease_net_best_case_usd: float | None
    machine_vs_peer_index: float
    retire_date: str | None
    zone_id: str
    active_days: int
    rank_vs_peers: int
    rank_luck_aware: int
    luck_z: float
    hit_rate_z: float
    primary_factors: str | None
    recommended_alternative: str


class Executive(BaseModel):
    verdict: Verdict
    bottom10: list[BottomMachine]
    portfolios: list[Portfolio]
    kpis: dict[str, float]
    promotion: Record
    council_claims: int
    council_verified: int
    floor_candidates: int
    floor_planning_positive: int
    floor_best_case_positive: int
    inspection_cost_usd: float | None


class MachineRow(BaseModel):
    machine_id: str
    config_id: str
    manufacturer: str
    zone_id: str
    zone_name: str
    bank_id: str | None
    house_win_usd: float
    theo_usd: float
    theo_per_available_hour_usd: float
    available_hours: float
    availability_rate: float
    downtime_hours: float | None
    rank_raw: int
    rank_luck_aware: int
    rank_vs_peers: int
    luck_z: float
    hit_rate_z: float
    payout_anomaly: bool
    manager_rank: int | None
    verdict: str | None
    lease_net_best_case_usd: float | None
    robustness: str | None


class MachinePage(BaseModel):
    total: int
    offset: int
    limit: int
    rows: list[MachineRow]


class MachineDetail(BaseModel):
    machine: Record
    zone_name: str
    bank_id: str | None
    investigation: Record | None
    robustness: Record | None
    verification: Record | None
    candidate: Record | None
    council_claims: list[Record]


class Demand(BaseModel):
    period: dict[str, str]
    exploratory: bool
    totals: Record
    weekly: list[Record]
    daily: list[Record]
    zone_monthly: list[Record]
    explanations: list[Record]


class BankList(BaseModel):
    period: dict[str, str]
    exploratory: bool
    banks: list[Record]


class BankDetail(BaseModel):
    bank_id: str
    period: dict[str, str]
    totals: Record
    daily: list[Record]
    machines: list[str]


class Downtime(BaseModel):
    totals: Record
    by_manufacturer: list[Record]
    by_hour: list[Record]
    by_zone_month: list[Record]


class Players(BaseModel):
    summary: Record
    tiers: list[Record]
    population: str = "tracked (carded) play only; never combined with all-play meters"


class Comps(BaseModel):
    months: list[Record]


class CouncilSummary(BaseModel):
    agents: list[Record]
    decisions: list[Record]
    machines: list[Record]
    claims: list[Record]


class CouncilDecision(BaseModel):
    decision_id: str
    events: list[Record]
    whispers: list[Record]
    portfolio_changed: bool
    scenario_flips: list[str]


class Portfolios(BaseModel):
    options: list[Portfolio]
    passports: list[Record]
    measurement_plans: list[Record]
    promotion: Record
    constraints: list[Record]
    catalog: list[Record]


class Scenarios(BaseModel):
    promotion: Record
    stress: list[Record]
    reversals: list[Record]
    lease_operating_days: int | None


class EvidencePassport(BaseModel):
    kind: str
    id: str
    title: str
    fields: list[list[str]]
    links: list[str]


class EvidenceList(BaseModel):
    total: int
    claims: list[Record]
    classifications: dict[str, int]
    passports: list[Record]
    machines: list[str]
    verification: list[Record]


class Forecast(BaseModel):
    comparison: list[Record]
    holdout: list[Record]
    decision_impact: list[Record]
    protocol: Record


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=400)
    machine_context: str | None = Field(default=None, pattern=r"^M-\d{4}$")


class AskAction(BaseModel):
    type: Literal[
        "select_entity",
        "open_answers",
        "set_filters",
        "compare_portfolios",
        "get_evidence",
        "explain_reversal",
        "open_validation",
        "open_council",
    ]
    view: Literal[
        "overview",
        "machines",
        "operations",
        "council",
        "scenarios",
        "investment",
        "evidence",
        "validation",
        "answers",
    ]
    args: dict[str, str]


class AskResponse(BaseModel):
    status: Literal["OK", "UNAVAILABLE", "AMBIGUOUS", "UNSUPPORTED", "REFUSED"]
    intent: str
    conclusion: str
    support: list[str]
    period: str
    evidence: str
    uncertainty: str | None
    premise_correction: str | None
    action: AskAction | None


class ErrorBody(BaseModel):
    error: str
    detail: str
    recovery: str
