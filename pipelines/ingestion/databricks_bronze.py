"""Phase 2 ingestion: official Parquet files in a UC volume -> Delta bronze tables.

Files are uploaded unchanged (scripts/databricks_upload.sh) and verified against the
official SHA-256 before loading. Each table keeps the official name, so all analytics
SQL runs unchanged. Bronze tables are replaced on every load (idempotent).
"""

from __future__ import annotations

import hashlib
from typing import Any

from databricks.sdk import WorkspaceClient

from backend.repositories.databricks_repo import DatabricksRepository
from pipelines.ingestion.catalog import TABLES_BY_NAME


def volume_root(catalog: str, schema: str, volume: str = "raw") -> str:
    return f"/Volumes/{catalog}/{schema}/{volume}"


def verify_volume_files(ws: WorkspaceClient, manifest: dict[str, Any], root: str
                        ) -> list[dict[str, Any]]:
    """Re-hash every uploaded file (Files API; no compute) against the manifest."""
    out = []
    for t in manifest["tables"]:
        if t["status"] == "missing":
            continue
        data = ws.files.download(f"{root}/{t['source_path']}").contents.read()  # type: ignore[union-attr]
        digest = hashlib.sha256(data).hexdigest()
        out.append({"table": t["table"], "bytes": len(data), "sha256": digest,
                    "verified": digest == t["sha256"] and len(data) == t["bytes"]})
    return out


def load_bronze(repo: DatabricksRepository, manifest: dict[str, Any], root: str
                ) -> list[dict[str, Any]]:
    """CREATE OR REPLACE each bronze table and check row counts against the manifest."""
    results = []
    for t in manifest["tables"]:
        if t["status"] == "missing":
            continue
        spec = TABLES_BY_NAME[t["table"]]
        comment = (f"Official Dashboard Royale {manifest['dataset_version']} | grain: "
                   f"{spec.grain} | source sha256 {t['sha256'][:16]} | origin "
                   f"{spec.origin.value}").replace("'", "")
        repo.execute(f"""
            CREATE OR REPLACE TABLE `{spec.name}`
            COMMENT '{comment}'
            AS SELECT * FROM read_files('{root}/{spec.parquet_path}', format => 'parquet')""")
        rows = int(repo.scalar(f"SELECT count(*) FROM `{spec.name}`"))
        results.append({"table": spec.name, "rows": rows, "expected_rows": t["rows"],
                        "status": "pass" if rows == t["rows"] else "fail"})
    return results
