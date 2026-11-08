"""Sidecar export for the dashboard: grains the ch_* contracts do not carry.

- floor_day: property_day sums per gaming date (date-filterable floor demand)
- bank_day: prepared_daily_view sums per bank x gaming date, active rows only (bank drill-down)
- machine_bank: last active bank / zone per machine
- audit_*: copies of reports/audit/*.json (hardening audit, local run)

Money is exported in integer cents so filtered totals are exact sums; ratios must be
recomputed as ratio-of-sums in the UI. Read-only: reads the official parquet files.
Writes web/public/data/sidecar/ with a SHA-256 manifest.

Usage: uv run python scripts/export_dashboard_sidecar.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import get_settings  # noqa: E402

OUT = ROOT / "web" / "public" / "data" / "sidecar"
SNAPSHOT = "chf-v1:bc5e8ccc5d88a490"


def main() -> int:
    d = Path(get_settings().challenge_data_dir)
    pv = d / "1_prepared_views" / "prepared_daily_view.parquet"
    pdy = d / "1_prepared_views" / "property_day.parquet"
    con = duckdb.connect()
    floor = con.sql(f"""SELECT strftime(gaming_date, '%Y-%m-%d') d,
        CAST(round(coin_in_usd*100) AS BIGINT) ci, CAST(round(house_win_usd*100) AS BIGINT) hw,
        CAST(round(theo_usd*100) AS BIGINT) th, available_machine_hours ah,
        CAST(round(comp_cost_usd*100) AS BIGINT) cc, coalesce(events_active, '') ev,
        active_machines am
        FROM '{pdy}' WHERE gaming_date BETWEEN DATE '2025-01-01' AND DATE '2025-06-30'
        ORDER BY 1""").fetchall()
    dates = [r[0] for r in floor]
    bank = con.sql(f"""SELECT bank_id, any_value(zone_id) zone_id,
        strftime(gaming_date,'%Y-%m-%d') d,
        CAST(sum(round(coin_in_usd*100)) AS BIGINT) ci,
        CAST(sum(round(house_win_usd*100)) AS BIGINT) hw,
        CAST(sum(round(theo_usd*100)) AS BIGINT) th, sum(available_hours) ah,
        count(*) md
        FROM '{pv}' WHERE active GROUP BY bank_id, gaming_date ORDER BY 1, 3""").fetchall()
    banks: dict[str, dict] = {}
    idx = {x: i for i, x in enumerate(dates)}
    for b, z, dt, ci, hw, th, ah, md in bank:
        e = banks.setdefault(b, {"bank_id": b, "zone_id": z,
                                 **{k: [0] * len(dates) for k in ("ci", "hw", "th", "md")},
                                 "ah": [0.0] * len(dates)})
        i = idx[dt]
        e["ci"][i], e["hw"][i], e["th"][i], e["md"][i] = ci, hw, th, md
        e["ah"][i] = round(ah, 4)
    mb = con.sql(f"""SELECT machine_id, arg_max(bank_id, gaming_date) bank_id,
        arg_max(zone_id, gaming_date) zone_id FROM '{pv}' WHERE active GROUP BY 1 ORDER BY 1"""
                 ).fetchall()
    payloads = {
        "floor_day": {"unit": "integer cents (ci coin-in, hw house win, th theo, cc comp cost); "
                      "ah available machine-hours", "rows": [dict(zip(
                          ("d", "ci", "hw", "th", "ah", "cc", "ev", "am"), r, strict=True))
                          for r in floor]},
        "bank_day": {"unit": "integer cents per gaming date, active machine-days only; "
                     "ah available hours; md machine-days", "dates": dates,
                     "banks": list(banks.values())},
        "machine_bank": [{"machine_id": m, "bank_id": b, "zone_id": z} for m, b, z in mb],
    }
    mp = ROOT / "data" / "processed" / "step5" / "duckdb" / "action_measurement_plans.parquet"
    payloads["measurement_plans"] = con.sql(
        f"SELECT action_id, investment, quantity, expected_effect, evidence_classification, "
        f"uncertainty, baseline_kpi, observation_period, comparison_method, feasibility, "
        f"confounders, success_threshold, stop_or_revise, unit_cost, total_cost, status "
        f"FROM '{mp}'").df().to_dict(orient="records")
    for name in ("a3_a4_verification", "b4_robustness_matrix", "c_promotion_portfolio",
                 "b_inputs"):
        payloads[f"audit_{name}"] = json.loads(
            (ROOT / "reports" / "audit" / f"{name}.json").read_text())
    tmp = OUT.with_name("sidecar.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    files = []
    for name, obj in payloads.items():
        text = json.dumps(obj, separators=(",", ":"), default=str)
        (tmp / f"{name}.json").write_text(text)
        files.append({"dataset": name, "file": f"{name}.json",
                      "sha256": hashlib.sha256(text.encode()).hexdigest()})
    manifest = {"snapshot_id": SNAPSHOT, "source": "official parquet (local) + reports/audit",
                "exported_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "files": files,
                "notes": "Sidecar grains for date filtering and bank drill-down; audit "
                         "results are from scripts/run_audit.py (local run)."}
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1))
    shutil.rmtree(OUT, ignore_errors=True)
    tmp.rename(OUT)
    print(json.dumps({f["dataset"]: (OUT / f["file"]).stat().st_size for f in files}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
