"""Step 5 temporal-validity, decision-link and reproducibility tests (synthetic fixtures)."""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from models import forecasting as F
from models.canonical import canonical_fingerprint, quantise


def series(n: int = 140, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    weekly = np.array([0, -5, -8, -3, 10, 20, 12], float)[idx.day_of_week]
    return pd.Series(100 + weekly + rng.normal(0, 1, n), index=idx)


def test_forecast_inside_training_window_rejected():
    s = series()
    with pytest.raises(F.LeakageError):
        F.weekday_mean(s, pd.DatetimeIndex([s.index[-5]]))
    with pytest.raises(F.LeakageError):
        F.holt_winters(s, pd.DatetimeIndex([s.index[-1]]), None)


def test_random_or_gapped_split_rejected():
    s = series()
    with pytest.raises(F.LeakageError):  # forecast must start the day after training ends
        F.holt_winters(s.iloc[:100], pd.date_range(s.index[105], periods=5), None)


def test_future_values_cannot_influence_forecasts():
    s = series()
    hist, fut = s.iloc[:120], s.index[120:]
    a = F.holt_winters(hist, fut, "add")
    s2 = s.copy()
    s2.iloc[120:] = 1e9  # poison the future
    b = F.holt_winters(s2.iloc[:120], fut, "add")
    assert np.allclose(a, b)
    assert np.allclose(F.weekday_mean(hist, fut), F.weekday_mean(s2.iloc[:120], fut))


def test_event_counterfactual_uses_only_prior_data():
    s = series(181)
    start = s.index[150]
    events = pd.DataFrame({"event_id": ["EV-P-X"], "start_date": [start.date()],
                           "end_date": [(start + pd.Timedelta(days=6)).date()]})
    a = F.event_counterfactuals(s, events, None, set())
    s2 = s.copy()
    s2.loc[start + pd.Timedelta(days=7):] = 1e9  # after the event: must not matter
    b = F.event_counterfactuals(s2, events, None, set())
    assert np.allclose(a.candidate_counterfactual, b.candidate_counterfactual)
    assert np.allclose(a.baseline_counterfactual, b.baseline_counterfactual)
    assert (pd.to_datetime(a.issued_after) < pd.to_datetime(a.gaming_date)).all()


def test_metrics_reproduce_and_identical_rows():
    act = np.array([10.0, 20.0, 30.0])
    m = F.metrics(act, np.array([12.0, 18.0, 33.0]))
    assert m["mae"] == pytest.approx(7 / 3)
    assert m["bias"] == pytest.approx(1.0)
    assert m["wape"] == pytest.approx(7 / 60)


def test_canonical_hash_absorbs_float_noise_not_real_changes():
    class A:
        def __init__(self, v: float) -> None:
            self.value, self.valid = v, True

    class M:
        def __init__(self, f: dict, a: dict) -> None:
            self.facts, self.assumptions = f, {k: A(v) for k, v in a.items()}
    base = M({"b40_theo_per_day": 13337.890088, "floor_contribution_factor": 0.9468},
             {"A07_comp_cost_saving_rate": 0.0011199821668268373})
    noisy = M({"b40_theo_per_day": 13337.890088 * (1 + 3e-15),
               "floor_contribution_factor": 0.9468 * (1 + 1e-12)},
              {"A07_comp_cost_saving_rate": 0.0011199821668268408})
    real = M({"b40_theo_per_day": 13338.0, "floor_contribution_factor": 0.9468},
             {"A07_comp_cost_saving_rate": 0.0011199821668268373})
    assert canonical_fingerprint(base, "v") == canonical_fingerprint(noisy, "v")
    assert canonical_fingerprint(base, "v") != canonical_fingerprint(real, "v")
    assert quantise("b40_theo_per_day", 1.005) == "1.00"  # banker's rounding, documented


def test_no_credentials_in_outputs():
    pat = re.compile(r"(dapi[0-9a-f]{16,}|Bearer\s+[A-Za-z0-9._-]{20,}|sk-[A-Za-z0-9]{20,})")
    roots = [Path("reports"), Path("data/processed")]
    hits = [p for r in roots if r.exists() for p in r.rglob("*")
            if p.is_file() and p.suffix in {".json", ".md", ".jsonl", ".txt"}
            and pat.search(p.read_text(errors="ignore"))]
    assert hits == []
