"""Evidence provenance records.

Every consequential analytical result is stored as an EvidenceRecord. IDs are
deterministic (hash of calculation, filters, date range and dataset fingerprint), so
re-running the same calculation on the same data yields the same ID, and a data change
yields a new one. There are no confidence scores: validation_state says how the result
was checked, and uncertainty carries the actual interval or test statistic.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, computed_field


class ValidationState(StrEnum):
    RECONCILED = "reconciled"  # matched an independent recomputation
    TESTED = "tested"  # statistical test executed; see uncertainty
    DESCRIPTIVE = "descriptive"  # computed, not independently checked
    UNVERIFIED = "unverified"  # assumption or external claim not yet checked
    REFUTED = "refuted"  # a test contradicted it; kept for transparency


class EvidenceRecord(BaseModel):
    dataset_fingerprint: str
    source_tables: list[str]
    calculation_id: str = Field(description="Stable name of the function / metric used")
    metric: str
    filters: dict[str, Any] = Field(default_factory=dict)
    date_range: tuple[str, str]
    result: Any
    unit: str
    uncertainty: dict[str, Any] | None = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    validation_state: ValidationState
    claim: str = Field(description="Plain-language statement the result supports")
    domain: str
    created_at_utc: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_id(self) -> str:
        key = json.dumps(
            [self.dataset_fingerprint, self.calculation_id, self.metric,
             sorted(self.filters.items()), list(self.date_range)],
            default=str, sort_keys=True)
        return "EV-" + hashlib.sha256(key.encode()).hexdigest()[:12].upper()
