"""Expose official tables to the analytics layer through the repository contract.

Raw Parquet files are only read, never written: each table becomes a DuckDB view.
In Phase 2 the same table names resolve to Delta tables in Unity Catalog.
"""

from __future__ import annotations

from pathlib import Path

from backend.repositories.duckdb_repo import DuckDBRepository
from config.settings import Settings, get_settings

from .catalog import TABLES, TableSpec


class MissingSourceError(FileNotFoundError):
    pass


def data_dir(settings: Settings | None = None) -> Path:
    return Path((settings or get_settings()).challenge_data_dir)


def available_tables(root: Path) -> tuple[list[TableSpec], list[TableSpec]]:
    present: list[TableSpec] = []
    missing: list[TableSpec] = []
    for spec in TABLES:
        (present if (root / spec.parquet_path).exists() else missing).append(spec)
    return present, missing


def open_local_repository(
    settings: Settings | None = None, db_path: str = ":memory:"
) -> DuckDBRepository:
    """Return a repository with every available official table registered as a view.

    Raises MissingSourceError if a required table is absent; optional tables are skipped.
    """
    root = data_dir(settings)
    present, missing = available_tables(root)
    required_missing = [s.name for s in missing if s.required]
    if required_missing:
        raise MissingSourceError(
            f"Required tables missing under {root}: {required_missing}. "
            "Run scripts/fetch_data.sh"
        )
    repo = DuckDBRepository(db_path)
    for spec in present:
        repo.register_parquet_view(spec.name, str((root / spec.parquet_path).resolve()))
    return repo
