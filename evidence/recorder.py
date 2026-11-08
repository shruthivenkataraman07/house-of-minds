"""Lightweight evidence store (JSON Lines locally; a Delta table in Phase 2)."""

from __future__ import annotations

import json
from pathlib import Path

from .schema import EvidenceRecord


class EvidenceRecorder:
    def __init__(self, path: str | Path, dataset_fingerprint: str) -> None:
        self.path = Path(path)
        self.fingerprint = dataset_fingerprint
        self._records: dict[str, EvidenceRecord] = {}

    def record(self, **fields: object) -> str:
        rec = EvidenceRecord(dataset_fingerprint=self.fingerprint, **fields)  # type: ignore[arg-type]
        self._records[rec.evidence_id] = rec  # same calculation -> same id, latest wins
        return rec.evidence_id

    def get(self, evidence_id: str) -> EvidenceRecord:
        return self._records[evidence_id]

    @property
    def records(self) -> list[EvidenceRecord]:
        return list(self._records.values())

    def flush(self) -> Path:
        """Rewrite the store with this run's records (one JSON object per line)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w") as f:
            for rec in self._records.values():
                f.write(json.dumps(rec.model_dump(mode="json"), default=str) + "\n")
        return self.path

    @staticmethod
    def load(path: str | Path) -> list[EvidenceRecord]:
        p = Path(path)
        if not p.exists():
            return []
        out = []
        for line in p.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                d.pop("evidence_id", None)
                out.append(EvidenceRecord(**d))
        return out
