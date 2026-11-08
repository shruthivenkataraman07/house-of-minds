from datetime import date

import pandas as pd
import pytest

from models.temporal_split import ALLOWED_FEATURES, FEATURES, assert_no_leakage, assign_split


def test_split_boundaries():
    assert assign_split(date(2025, 3, 31)) == "train_inner"
    assert assign_split(date(2025, 4, 1)) == "validation_inner"
    assert assign_split(date(2025, 4, 30)) == "validation_inner"
    assert assign_split(date(2025, 5, 1)) == "holdout"
    assert assign_split(date(2025, 6, 30)) == "holdout"
    with pytest.raises(ValueError):
        assign_split(date(2025, 7, 1))


def test_leaky_features_blocked():
    leaky = [f.name for f in FEATURES if f.leakage_risk == "high"]
    assert "lag_coin_in_7d_mean" in leaky and "event_any" in leaky
    assert not set(leaky) & set(ALLOWED_FEATURES)
    df = pd.DataFrame({"gaming_date": [date(2025, 4, 30), date(2025, 5, 1)],
                       "split": ["validation_inner", "holdout"]})
    assert_no_leakage(df, ["weekday"])
    with pytest.raises(ValueError):
        assert_no_leakage(df, ["lag_coin_in_7d_mean"])
