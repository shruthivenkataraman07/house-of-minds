"""Export a validated, public-safe analytical snapshot for the Next.js app.

Pulls the Step 6 serving tables live from Unity Catalog, re-checks row counts against the
warehouse, rejects personal columns and secret-like content, and writes JSON plus a
manifest (rows, SHA-256, snapshot id) to web/public/data/current/.

Usage: uv run python scripts/export_web_snapshot.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.repositories.databricks_repo import DatabricksRepository  # noqa: E402
from config.settings import get_settings  # noqa: E402
from vault.extra import scan_public  # noqa: E402

DATASETS = {
    "dash_executive_kpis": None, "dash_machine_intelligence": None,
    "dash_investment_portfolios": None, "dash_scenario_surface": None,
    "dash_council_activity": None, "dash_evidence_validation": None,
    "dash_model_evaluation": None, "dash_decision_passports": None,
    "aibi_metric_definitions": None,
    # Whisper Network graph edges (council messages; no personal data)
    "council_whispers": "SELECT config, message_id, sender_agent_id, recipient_agent_id, "
                        "message_type, claim_id, origin_claim_id, origin_agent_id, "
                        "forward_chain, round_number, sequence, message_status, "
                        "uncertainty_status, flagged_retracted_origin, statement "
                        "FROM council_whispers",
}
OUT = ROOT / "web" / "public" / "data" / "current"


def main() -> int:
    s = get_settings()
    repo = DatabricksRepository(s.databricks_warehouse_id or "", s.databricks_catalog,
                                s.databricks_schema, s.databricks_profile)
    tmp = OUT.with_name("current.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    files, problems = [], {}
    snapshot = None
    for name, sql in DATASETS.items():
        df = repo.query_df(sql or f"SELECT * FROM {name}")
        df = df.drop(columns=[c for c in df.columns if c == "_rescued_data"])
        n_wh = int(repo.scalar(f"SELECT count(*) FROM {name}"))
        bad = scan_public(df)
        if bad or len(df) != n_wh:
            problems[name] = {"unsafe": bad, "rows": len(df), "warehouse_rows": n_wh}
            continue
        if "snapshot_id" in df.columns and snapshot is None:
            snapshot = str(df.snapshot_id.dropna().iloc[0])
        text = df.to_json(orient="records", date_format="iso", default_handler=str)
        path = tmp / f"{name}.json"
        path.write_text(text)
        files.append({"dataset": name, "file": path.name, "rows": len(df),
                      "warehouse_rows": n_wh,
                      "sha256": hashlib.sha256(text.encode()).hexdigest(),
                      "columns": list(df.columns)})
    contract = ROOT / "semantic" / "ask_the_house_contract.json"
    shutil.copy(contract, tmp / "ask_the_house_contract.json")
    if problems:
        print("EXPORT REJECTED:", json.dumps(problems, indent=1))
        shutil.rmtree(tmp)
        return 1
    manifest = {"snapshot_id": snapshot, "source": f"{s.databricks_catalog}."
                f"{s.databricks_schema} @ {s.databricks_host}",
                "exported_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "files": files, "semantic_contract": "ask_the_house_contract.json",
                "notes": "Public-safe: aggregated analytics only; no player/guest rows; "
                         "modeled values are not realised profit."}
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1))
    shutil.rmtree(OUT, ignore_errors=True)
    tmp.rename(OUT)
    print(json.dumps({"snapshot": snapshot, "files": [(f["dataset"], f["rows"])
                                                      for f in files]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
