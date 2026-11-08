"""Dataset manifest: what was acquired, its fingerprint, and whether it matches the release."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from .catalog import TABLES


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_commit(repo_root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_manifest(data_root: Path) -> dict[str, Any]:
    """Hash every catalogued Parquet file and compare with the official manifest.json."""
    official_path = data_root / "manifest.json"
    official = json.loads(official_path.read_text()) if official_path.exists() else {}
    official_files = {f["path"]: f for f in official.get("files", [])}

    con = duckdb.connect()
    entries = []
    for spec in TABLES:
        path = data_root / spec.parquet_path
        entry: dict[str, Any] = {
            "table": spec.name,
            "source_path": spec.parquet_path,
            "required": spec.required,
            "origin": spec.origin.value,
            "documented_grain": spec.grain,
        }
        if not path.exists():
            entry["status"] = "missing"
            entries.append(entry)
            continue
        digest = sha256_file(path)
        rows = con.execute(
            "SELECT count(*) FROM read_parquet(?)", [str(path)]
        ).fetchone()[0]  # type: ignore[index]
        ref = official_files.get(spec.parquet_path, {})
        checks = {
            "sha256_matches_official": ref.get("sha256") == digest if ref else None,
            "bytes_match_official": ref.get("bytes") == path.stat().st_size if ref else None,
            "rows_match_official": ref.get("rows") == rows if ref else None,
        }
        ok = all(v is True for v in checks.values())
        entry.update(
            bytes=path.stat().st_size,
            sha256=digest,
            rows=rows,
            **checks,
            status="verified" if ok else ("unverified" if not ref else "mismatch"),
        )
        entries.append(entry)

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset": official.get("dataset"),
        "dataset_version": official.get("version"),
        "world_id": official.get("world_id"),
        "window_local": official.get("window_local"),
        "source_repository": "https://github.com/tamu-datathon-org/dashboard-royale",
        "source_commit": _git_commit(data_root.parent),
        "acquisition": "git clone --depth 1 (scripts/fetch_data.sh); files kept read-only",
        "fingerprint": dataset_fingerprint(entries),
        "tables": entries,
        "missing_required": [e["table"] for e in entries
                             if e["status"] == "missing" and e["required"]],
        "missing_optional": [e["table"] for e in entries
                             if e["status"] == "missing" and not e["required"]],
    }


def dataset_fingerprint(entries: list[dict[str, Any]]) -> str:
    """Stable short hash over (table, sha256) pairs; used in every evidence record."""
    parts = sorted(f"{e['table']}:{e.get('sha256', 'missing')}" for e in entries)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
