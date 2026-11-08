from evidence.recorder import EvidenceRecorder
from evidence.schema import EvidenceRecord, ValidationState


def make(**kw):
    base = dict(dataset_fingerprint="abc", source_tables=["machine_day"],
                calculation_id="calc.x", metric="m", date_range=("2025-01-01", "2025-06-30"),
                result=1, unit="USD", validation_state=ValidationState.TESTED,
                claim="c", domain="d")
    base.update(kw)
    return EvidenceRecord(**base)


def test_id_deterministic_and_sensitive():
    a, b = make(), make(result=2)
    assert a.evidence_id == b.evidence_id  # same calculation, same id
    assert a.evidence_id.startswith("EV-")
    assert make(filters={"zone": "Z-B40"}).evidence_id != a.evidence_id
    assert make(dataset_fingerprint="other").evidence_id != a.evidence_id


def test_no_confidence_score_field():
    assert "confidence" not in EvidenceRecord.model_fields


def test_recorder_roundtrip(tmp_path):
    rec = EvidenceRecorder(tmp_path / "ev.jsonl", "fp1")
    eid = rec.record(source_tables=["t"], calculation_id="c", metric="m",
                     date_range=("2025-01-01", "2025-01-02"), result={"x": 1}, unit="u",
                     validation_state=ValidationState.RECONCILED, claim="c", domain="d")
    rec.flush()
    loaded = EvidenceRecorder.load(tmp_path / "ev.jsonl")
    assert len(loaded) == 1 and loaded[0].evidence_id == eid
