"""Data sources for the dashboard API.

Mode A (snapshot): the validated export in web/public/data/current (+ sidecar), every file
checked against its manifest SHA-256 and row count. Works without credentials.
Mode B (databricks): the same contracts read live from allowlisted Unity Catalog tables
through the existing DatabricksRepository (server-side OAuth / service principal), with a
TTL cache. Datasets that exist only in the sidecar (daily grains, audit) always come from
the snapshot, and every response reports which source served it.

Read-only: the only SQL issued is `SELECT * FROM <allowlisted table>`; no user input
reaches a query.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "web" / "public" / "data"

# Datasets the live mode may read from Unity Catalog (exact table names; nothing else).
LIVE_TABLES = frozenset(
    {
        "ch_executive_verdict",
        "ch_manager_bottom10",
        "ch_machine_investigation",
        "ch_replacement_candidates",
        "ch_portfolio_comparison",
        "ch_council_manager_review",
        "ch_floor_demand_monthly",
        "ch_floor_demand_weekly",
        "ch_zone_demand",
        "ch_zone_traffic",
        "ch_demand_explanations",
        "ch_downtime_economics",
        "ch_downtime_by_hour",
        "ch_player_outcomes",
        "ch_player_outcomes_by_tier",
        "ch_loyalty_comps",
        "dash_executive_kpis",
        "dash_machine_intelligence",
        "dash_scenario_surface",
        "dash_council_activity",
        "dash_evidence_validation",
        "dash_model_evaluation",
        "dash_decision_passports",
        "council_whispers",
        "forecast_baseline_comparison",
        "decision_model_impact",
        "aibi_metric_definitions",
    }
)


class DataUnavailable(RuntimeError):
    """A dataset could not be served by any configured source."""


@dataclass
class Snapshot:
    """Verified snapshot reader (Mode A)."""

    root: Path = DATA
    _cache: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _manifest(self, sub: str) -> dict[str, Any]:
        key = f"__manifest_{sub}"
        if key not in self._cache:
            path = self.root / sub / "manifest.json"
            if not path.exists():
                raise DataUnavailable(f"snapshot manifest missing: {sub}")
            self._cache[key] = json.loads(path.read_text())
        return self._cache[key]

    def meta(self) -> dict[str, Any]:
        cur, side = self._manifest("current"), self._manifest("sidecar")
        return {
            "snapshot_id": cur["snapshot_id"],
            "exported_at_utc": cur["exported_at_utc"],
            "sidecar_snapshot_id": side["snapshot_id"],
            "sidecar_exported_at_utc": side["exported_at_utc"],
            "files": len(cur["files"]) + len(side["files"]),
        }

    def get(self, name: str) -> Any:
        with self._lock:
            if name in self._cache:
                return self._cache[name]
            for sub in ("current", "sidecar"):
                m = self._manifest(sub)
                e = next((f for f in m["files"] if f["dataset"] == name), None)
                if e is None:
                    continue
                text = (self.root / sub / e["file"]).read_text()
                if hashlib.sha256(text.encode()).hexdigest() != e["sha256"]:
                    raise DataUnavailable(f"checksum mismatch: {sub}/{name}")
                data = json.loads(text)
                if "rows" in e and isinstance(data, list) and len(data) != e["rows"]:
                    raise DataUnavailable(f"row count mismatch: {sub}/{name}")
                self._cache[name] = data
                return data
            raise DataUnavailable(f"dataset not in snapshot: {name}")


class Live:
    """Unity Catalog reader (Mode B). Lazily connects; caches each table for `ttl` seconds."""

    def __init__(self, repo_factory: Any, ttl: float = 900.0) -> None:
        self._factory = repo_factory
        self._repo: Any = None
        self._ttl = ttl
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._lock = threading.Lock()
        self.last_error: str | None = None

    def get(self, name: str) -> list[dict[str, Any]]:
        if name not in LIVE_TABLES:
            raise DataUnavailable(f"not a live table: {name}")
        with self._lock:
            hit = self._cache.get(name)
            if hit and time.monotonic() - hit[0] < self._ttl:
                return hit[1]
            try:
                if self._repo is None:
                    self._repo = self._factory()
                df = self._repo.query_df(f"SELECT * FROM {name}")  # name is allowlisted
                df = df.drop(columns=[c for c in df.columns if c == "_rescued_data"])
                rows = json.loads(
                    df.to_json(orient="records", date_format="iso", default_handler=str)
                )
            except Exception as exc:  # connection, auth, timeout
                self.last_error = f"{type(exc).__name__}: {exc}"[:300]
                raise DataUnavailable(self.last_error) from exc
            self._cache[name] = (time.monotonic(), rows)
            self.last_error = None
            return rows


class DataSource:
    """Mode selection + per-dataset provenance. Snapshot is always the verified fallback."""

    def __init__(
        self, mode: str = "snapshot", live: Live | None = None, snapshot: Snapshot | None = None
    ) -> None:
        if mode not in ("snapshot", "databricks"):
            raise ValueError("HOM_DATA_MODE must be 'snapshot' or 'databricks'")
        self.mode = mode
        self.snapshot = snapshot or Snapshot()
        self.live = live
        self.served_from: dict[str, str] = {}

    def get(self, name: str) -> Any:
        if self.mode == "databricks" and self.live is not None and name in LIVE_TABLES:
            try:
                rows = self.live.get(name)
                self.served_from[name] = "databricks"
                return rows
            except DataUnavailable as exc:
                log.warning("live read failed for %s; serving snapshot: %s", name, exc)
        self.served_from[name] = "snapshot"
        return self.snapshot.get(name)

    def provenance(self, names: list[str]) -> str:
        srcs = {self.served_from.get(n, "snapshot") for n in names}
        return srcs.pop() if len(srcs) == 1 else "mixed"


_source: DataSource | None = None


def get_source() -> DataSource:
    global _source
    if _source is None:
        import os

        mode = os.environ.get("HOM_DATA_MODE", "snapshot")
        live = None
        if mode == "databricks":

            def factory() -> Any:
                from backend.repositories.databricks_repo import DatabricksRepository
                from config.settings import get_settings

                s = get_settings()
                if not s.databricks_warehouse_id:
                    raise DataUnavailable("DATABRICKS_WAREHOUSE_ID not set")
                return DatabricksRepository(
                    s.databricks_warehouse_id,
                    s.databricks_catalog,
                    s.databricks_schema,
                    s.databricks_profile,
                )

            live = Live(factory, float(os.environ.get("HOM_CACHE_TTL_S", "900")))
        _source = DataSource(mode, live)
    return _source
