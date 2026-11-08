"""Phase 2 acceptance gates: Databricks results must match the local DuckDB results.

Usage: uv run python scripts/compare_backends.py
Compares data/processed/*.parquet with data/processed/databricks/*.parquet,
reports/reconciliation.json with reports/databricks/reconciliation.json, and the
evidence IDs of both ledgers. Exit code 0 only if every gate passes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOCAL, REMOTE = ROOT / "data" / "processed", ROOT / "data" / "processed" / "databricks"
MONEY_ATOL, FLOAT_RTOL = 0.01, 1e-6
# Bootstrap columns use a seeded RNG on identical inputs, so they must match too; ties in
# rank columns are broken by machine_id order in both engines.
KEYS = {"contract_machine_performance": ["machine_id"],
        "contract_demand_day": ["gaming_date"],
        "contract_downtime_month": ["month", "manufacturer", "zone_id"],
        "contract_guest_month": ["period_month", "opening_tier"],
        "contract_comp_day": ["gaming_date"],
        "contract_intervention_options": ["action_type_id"],
        "modeling_daily_floor": ["gaming_date"]}


def compare_table(name: str) -> list[str]:
    a = pd.read_parquet(LOCAL / f"{name}.parquet")
    b = pd.read_parquet(REMOTE / f"{name}.parquet")
    keys = KEYS[name]
    problems = []
    if len(a) != len(b):
        return [f"{name}: rows {len(a)} vs {len(b)}"]
    a = a.astype({k: str for k in keys}).sort_values(keys).reset_index(drop=True)
    b = b.astype({k: str for k in keys}).sort_values(keys).reset_index(drop=True)
    for col in a.columns:
        x, y = a[col], b[col]
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            xv, yv = x.to_numpy(float), y.to_numpy(float)
            # Money: within one cent. Other floats (hours, ratios, bootstrap bounds):
            # relative 1e-6, because summation order differs between engines (observed
            # max deviations: 4.4e-7 h in downtime_hours, 2.5e-8 in a bootstrap bound).
            if col.endswith("_usd"):
                ok = np.isclose(xv, yv, rtol=0, atol=MONEY_ATOL, equal_nan=True)
            else:
                ok = np.isclose(xv, yv, rtol=FLOAT_RTOL, atol=1e-9, equal_nan=True)
            if not ok.all():
                problems.append(f"{name}.{col}: {int((~ok).sum())} rows differ "
                                f"(max {np.nanmax(np.abs(xv - yv)):.6g})")
        elif not (x.astype(str).fillna("") == y.astype(str).fillna("")).all():
            problems.append(f"{name}.{col}: values differ")
    return problems


def main() -> int:
    gates: dict[str, list[str]] = {}
    gates["contract tables"] = [p for n in KEYS for p in compare_table(n)]
    ra = json.loads((ROOT / "reports" / "reconciliation.json").read_text())
    rb = json.loads((ROOT / "reports" / "databricks" / "reconciliation.json").read_text())
    gates["reconciliation"] = [f"{y['test_id']}: {y['status']}" for y in rb
                               if y["status"] != "pass"]
    for x, y in zip(ra, rb, strict=True):
        for k, v in x["calculated_result"].items():
            w = y["calculated_result"].get(k)
            numeric = isinstance(v, (int, float)) and isinstance(w, (int, float))
            if numeric and not np.isclose(v, w, rtol=1e-9, atol=0.01):
                gates["reconciliation"].append(f"{x['test_id']}.{k}: {v} vs {w}")
    ea = {json.loads(line)["evidence_id"] for line in
          (LOCAL / "evidence_ledger.jsonl").read_text().splitlines()}
    eb = {json.loads(line)["evidence_id"] for line in
          (REMOTE / "evidence_ledger.jsonl").read_text().splitlines()}
    gates["evidence ids"] = [] if ea == eb else [f"{len(ea ^ eb)} ids differ"]
    for g, probs in gates.items():
        print(f"{'PASS' if not probs else 'FAIL'}: {g}")
        for p in probs[:20]:
            print("   ", p)
    return 0 if not any(gates.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
