"""The few SQL constructs that differ between DuckDB (Phase 1) and Databricks SQL (Phase 2).

Everything else in the analytics SQL is written in the common subset of both engines, so
formulas exist once. Repositories expose `dialect` ("duckdb" or "databricks").
"""

from __future__ import annotations

from typing import Any


def dialect_of(repo: Any) -> str:
    return getattr(repo, "dialect", "duckdb")


def ident(name: str, dialect: str) -> str:
    if dialect == "databricks":
        return "`" + name.replace("`", "``") + "`"
    return '"' + name.replace('"', '""') + '"'


def seconds_between(start: str, end: str, dialect: str) -> str:
    if dialect == "databricks":
        return f"timestampdiff(SECOND, {start}, {end})"
    return f"date_diff('second', {start}, {end})"


def days_between(start: str, end: str, dialect: str) -> str:
    if dialect == "databricks":
        return f"datediff({end}, {start})"
    return f"date_diff('day', {start}, {end})"


def local_hhmm(ts_utc: str, dialect: str, tz: str = "America/Los_Angeles") -> str:
    if dialect == "databricks":
        return f"date_format(from_utc_timestamp({ts_utc}, '{tz}'), 'HH:mm')"
    return f"strftime(timezone('{tz}', {ts_utc} AT TIME ZONE 'UTC'), '%H:%M')"


def year_month(date_expr: str) -> str:
    """Portable YYYY-MM (both engines accept CAST AS STRING and substr)."""
    return f"substr(CAST({date_expr} AS STRING), 1, 7)"
