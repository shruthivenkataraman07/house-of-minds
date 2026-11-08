"""Table profiling: structure, keys, nulls, ranges, coverage and referential integrity.

Profiles describe the data; they never modify it. Findings are classified as
confirmed_error, potential_anomaly, expected_behavior or unverified_assumption.
"""

from __future__ import annotations

from typing import Any

from analytics.sql_dialect import dialect_of, ident
from backend.repositories.base import AnalyticsRepository
from pipelines.ingestion.catalog import FOREIGN_KEYS, TABLES, TableSpec

NUMERIC_PREFIXES = ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "DOUBLE",
                    "FLOAT", "DECIMAL", "UBIGINT", "UINTEGER")
TEMPORAL_PREFIXES = ("DATE", "TIMESTAMP")

# Columns where nulls are documented business behaviour, not data errors.
EXPECTED_NULLS: dict[str, str] = {
    "location_id": "Null on documented off-floor machine-days (not installed / retired).",
    "availability_ratio": "Null on off-floor machine-days.",
    "occupancy_ratio": "Null when no available hours.",
    "observed_hold": "Undefined when coin-in is zero.",
    "theo_hold": "Undefined when coin-in is zero.",
    "carded_share": "Undefined when coin-in is zero.",
    "retire_date": "Machine still on the floor.",
    "effective_to_utc": "Placement still open.",
    "entries_count": "Counter offline; missing is not zero.",
    "player_id": "Uncarded POS sale or unlinked record.",
    "observed_visit_id": "Uncarded sale.",
    "comp_id": "Ticket not paid by a comp.",
    "benefit_id": "Award rows have no redeemed benefit.",
    "redeemed_pos_id": "Award rows have no POS ticket.",
    "source_segment_id": "Redemption rows have no earning segment.",
    "federal_holiday": "Not a holiday.",
    "events_active": "No event that day.",
    "closed_from_utc": "Walkway never closed.",
    "closed_to_utc": "Walkway never closed.",
    "closure_reason": "Walkway never closed.",
    "machine_id": "Incident not tied to a machine.",
    "zone_id": "Floor-wide assignment or off-floor row.",
    "age_band": "Documented as missing for some players.",
    "entity_id": "Rule applies to all entities.",
    "effective_to": "Open-ended rule.",
    "incompatibility_group": "Action has no conflict group.",
}


# Table-specific documented nulls.
EXPECTED_NULLS_BY_TABLE: dict[tuple[str, str], str] = {
    **{("prepared_daily_view", c): "Null on the 1,018 documented off-floor machine-days."
       for c in ("zone_id", "zone_name", "bank_id", "zone_entries_observed",
                 "zone_counter_coverage_hours")},
    **{("prepared_daily_view", c): "No prior gaming days for the first window day of each "
                                   "machine (310 machines)."
       for c in ("lag_coin_in_7d_mean_usd", "lag_downtime_7d_hours",
                 "lag_house_win_28d_usd")},
    **{("floor_locations", c): "Hierarchy: column applies only to some node types "
                               "(zone/bank/slot/outlet/entrance)."
       for c in ("parent_location_id", "bank_id", "outlet_id", "name", "capacity")},
    ("events", "source_url"): "Fictional property promotions have no public source.",
    **{("weather_daily", c): "NOAA convention: blank flag/time means no flag recorded."
       for c in ("tmax_mflag", "tmax_qflag", "tmax_sflag", "tmax_observation_time",
                 "tmin_mflag", "tmin_qflag", "tmin_sflag", "tmin_observation_time",
                 "prcp_mflag", "prcp_qflag", "prcp_sflag", "prcp_observation_time")},
}


_DIALECT = {"value": "duckdb"}


def _q(name: str) -> str:
    return ident(name, _DIALECT["value"])


def profile_table(repo: AnalyticsRepository, spec: TableSpec) -> dict[str, Any]:
    _DIALECT["value"] = dialect_of(repo)
    t = _q(spec.name)
    schema = repo.describe(spec.name)
    # One aggregate query per table (not per column): keeps remote warehouses fast.
    exprs = ["count(*) AS n_rows"]
    for i, col in enumerate(schema.itertuples()):
        c, dtype = _q(str(col.column_name)), str(col.column_type)
        exprs += [f"count(*) - count({c}) AS c{i}_nulls",
                  f"approx_count_distinct({c}) AS c{i}_distinct"]
        if dtype.startswith(NUMERIC_PREFIXES):
            exprs += [f"min({c}) AS c{i}_mn", f"max({c}) AS c{i}_mx",
                      f"avg({c}::DOUBLE) AS c{i}_mean",
                      f"count(*) FILTER (WHERE {c} < 0) AS c{i}_neg"]
        elif dtype.startswith(TEMPORAL_PREFIXES):
            exprs += [f"CAST(min({c}) AS STRING) AS c{i}_mn",
                      f"CAST(max({c}) AS STRING) AS c{i}_mx"]
    agg = repo.query_df(f"SELECT {', '.join(exprs)} FROM {t}").iloc[0]
    rows = int(agg.n_rows)
    columns: list[dict[str, Any]] = []
    findings: list[dict[str, str]] = []

    for i, col in enumerate(schema.itertuples()):
        name, dtype = str(col.column_name), str(col.column_type)
        c = _q(name)
        info: dict[str, Any] = {"name": name, "type": dtype}
        nulls = int(agg[f"c{i}_nulls"])
        info["null_count"] = nulls
        info["null_pct"] = round(100 * nulls / rows, 4) if rows else 0.0
        info["distinct_count"] = int(agg[f"c{i}_distinct"])
        if dtype.startswith(NUMERIC_PREFIXES):
            info.update(min=_py(agg[f"c{i}_mn"]), max=_py(agg[f"c{i}_mx"]),
                        mean=_py(agg[f"c{i}_mean"]), negative_count=int(agg[f"c{i}_neg"]))
        elif dtype.startswith(TEMPORAL_PREFIXES):
            info.update(min=str(agg[f"c{i}_mn"]), max=str(agg[f"c{i}_mx"]))
        elif dtype == "VARCHAR" and info["distinct_count"] <= 12:
            vals = repo.query_df(
                f"SELECT {c} v, count(*) n FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 12"
            )
            info["values"] = {str(r.v): int(r.n) for r in vals.itertuples()}
        if name.endswith("_cents"):
            info["unit"] = "integer cents"
        elif name.endswith("_usd"):
            info["unit"] = "dollars"
        columns.append(info)

        reason = EXPECTED_NULLS_BY_TABLE.get((spec.name, name)) or EXPECTED_NULLS.get(name)
        if nulls and reason:
            findings.append({"class": "expected_behavior", "column": name,
                             "detail": f"{nulls} nulls: {reason}"})
        elif nulls and name in spec.primary_key:
            findings.append({"class": "confirmed_error", "column": name,
                             "detail": f"{nulls} nulls in primary-key column"})
        elif nulls:
            findings.append({"class": "unverified_assumption", "column": name,
                             "detail": f"{nulls} nulls ({info['null_pct']}%) with no "
                                       "documented reason; treat as unknown, not zero"})
        if name in {"house_win_cents", "house_win_usd", "luck_residual_usd"} and \
                info.get("negative_count"):
            findings.append({"class": "expected_behavior", "column": name,
                             "detail": f"{info['negative_count']} negative values: machines "
                                       "can lose money on a day (documented)."})

    key_cols = ", ".join(_q(k) for k in spec.primary_key)
    dupes = int(repo.scalar(
        f"SELECT count(*) FROM (SELECT {key_cols} FROM {t} GROUP BY ALL HAVING count(*) > 1)"
    ))
    if dupes:
        findings.append({"class": "confirmed_error", "column": ",".join(spec.primary_key),
                         "detail": f"{dupes} duplicated documented keys"})

    coverage = {}
    for dc in spec.date_columns:
        if dc in schema.column_name.values:
            r = repo.query_df(
                f"SELECT min({_q(dc)}) mn, max({_q(dc)}) mx, "
                f"count(DISTINCT {_q(dc)}::DATE) n_days FROM {t}"
            ).iloc[0]
            coverage[dc] = {"min": str(r.mn), "max": str(r.mx), "distinct_days": int(r.n_days)}

    return {
        "table": spec.name,
        "source_path": spec.parquet_path,
        "documented_grain": spec.grain,
        "origin": spec.origin.value,
        "money_unit": spec.money_unit,
        "rows": rows,
        "column_count": len(columns),
        "primary_key": list(spec.primary_key),
        "duplicate_key_groups": dupes,
        "date_coverage": coverage,
        "columns": columns,
        "findings": findings,
    }


def referential_integrity(repo: AnalyticsRepository) -> list[dict[str, Any]]:
    """Orphan counts for documented foreign keys (nulls are not orphans)."""
    _DIALECT["value"] = dialect_of(repo)
    existing = set(repo.list_tables())
    out = []
    for child, ccol, parent, pcol in FOREIGN_KEYS:
        if child not in existing or parent not in existing:
            continue
        r = repo.query_df(
            f"SELECT count(*) FILTER (WHERE c.{_q(ccol)} IS NOT NULL) checked, "
            f"count(*) FILTER (WHERE c.{_q(ccol)} IS NOT NULL AND p.k IS NULL) orphans "
            f"FROM {_q(child)} c LEFT JOIN (SELECT DISTINCT {_q(pcol)} k FROM {_q(parent)}) p "
            f"ON c.{_q(ccol)} = p.k"
        ).iloc[0]
        out.append({"child": f"{child}.{ccol}", "parent": f"{parent}.{pcol}",
                    "checked_rows": int(r.checked), "orphans": int(r.orphans),
                    "status": "pass" if int(r.orphans) == 0 else "fail"})
    return out


def join_cardinality_risks(repo: AnalyticsRepository) -> list[dict[str, Any]]:
    """Joins that would fan out money columns if done naively."""
    # (label, joined-row SQL, baseline-row SQL)
    checks = [
        ("machine_day x placements on machine_id only (ignoring interval)",
         "SELECT count(*) FROM machine_day m JOIN placements p USING (machine_id)",
         "SELECT count(*) FROM machine_day"),
        ("active machine_day x placements on [effective_from, effective_to) interval",
         """SELECT count(*) FROM machine_day m
            JOIN calendar_day c USING (gaming_date)
            JOIN placements p ON p.machine_id = m.machine_id
             AND c.gaming_day_start_utc >= p.effective_from_utc
             AND (p.effective_to_utc IS NULL OR c.gaming_day_start_utc < p.effective_to_utc)
            WHERE m.active""",
         "SELECT count(*) FROM machine_day WHERE active"),
        ("sessions x fnb_transactions on player_id (two fact tables)",
         "SELECT count(*) FROM sessions s JOIN fnb_transactions f USING (player_id)",
         "SELECT count(*) FROM sessions"),
    ]
    out = []
    for label, sql, base_sql in checks:
        n, ref = int(repo.scalar(sql)), int(repo.scalar(base_sql))
        out.append({"join": label, "left_rows": ref, "joined_rows": n,
                    "fan_out": round(n / ref, 3) if ref else None,
                    "safe": n == ref})
    return out


def profile_all(repo: AnalyticsRepository) -> dict[str, Any]:
    existing = set(repo.list_tables())
    return {
        "tables": [profile_table(repo, s) for s in TABLES if s.name in existing],
        "referential_integrity": referential_integrity(repo),
        "join_cardinality": join_cardinality_risks(repo),
    }


def _py(v: Any) -> Any:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None if v is None else str(v)
    return int(f) if f.is_integer() and abs(f) < 2**53 else round(f, 6)
