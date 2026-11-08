"""Step 5 forecasting: weekday-mean baseline vs Holt-Winters candidate (protocol v1).

Every forecast function receives only the history up to its issuance date; leakage guards
raise if a forecast date is not strictly after the last training date.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from backend.repositories.base import AnalyticsRepository

TRAIN = (date(2025, 1, 1), date(2025, 3, 31))
VALID = (date(2025, 4, 1), date(2025, 4, 30))
HOLDOUT = (date(2025, 5, 1), date(2025, 6, 30))
TRENDS = (None, "add")  # protocol: trend in {none, additive damped}
SEASON = 7
INTERVAL = (0.10, 0.90)


class LeakageError(ValueError):
    pass


def load_series(repo: AnalyticsRepository) -> pd.Series:
    d = repo.query_df("SELECT gaming_date, theo_usd::DOUBLE theo FROM property_day "
                      "ORDER BY gaming_date")
    s = pd.Series(d.theo.to_numpy(), index=pd.DatetimeIndex(pd.to_datetime(d.gaming_date)),
                  name="theo_usd")
    if not s.index.is_monotonic_increasing or s.index.has_duplicates:
        raise ValueError("series not strictly ordered")
    return s.asfreq("D")


def _guard(history: pd.Series, dates: pd.DatetimeIndex) -> None:
    if len(dates) and dates.min() <= history.index.max():
        raise LeakageError(f"forecast date {dates.min().date()} not after last training date "
                           f"{history.index.max().date()}")


def weekday_mean(history: pd.Series, dates: pd.DatetimeIndex) -> np.ndarray:
    _guard(history, dates)
    means = history.groupby(history.index.day_of_week).mean()
    return np.array([means[d.day_of_week] for d in dates])


def holt_winters(history: pd.Series, dates: pd.DatetimeIndex, trend: str | None) -> np.ndarray:
    _guard(history, dates)
    if dates.min() != history.index.max() + pd.Timedelta(days=1):
        raise LeakageError("forecast must start the day after the last training date")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # convergence chatter; fit quality judged on holdout
        fit = ExponentialSmoothing(history, trend=trend, damped_trend=trend is not None,
                                   seasonal="add", seasonal_periods=SEASON,
                                   initialization_method="estimated").fit()
    return fit.forecast(len(dates)).to_numpy()


def window(s: pd.Series, span: tuple[date, date]) -> pd.Series:
    return s.loc[pd.Timestamp(span[0]):pd.Timestamp(span[1])]


def metrics(actual: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    err = pred - actual
    return {"mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err ** 2))),
            "bias": float(np.mean(err)),
            "wape": float(np.sum(np.abs(err)) / np.sum(np.abs(actual))), "n": int(len(actual))}


@dataclass
class ForecastRun:
    selected_trend: str | None
    validation_mae: dict[str, float]
    residual_q: tuple[float, float]
    holdout: pd.DataFrame  # date, actual, baseline, candidate, lo, hi, horizon, flags


def run_forecast_evaluation(s: pd.Series, event_days: set[pd.Timestamp]) -> ForecastRun:
    train, valid = window(s, (TRAIN[0], TRAIN[1])), window(s, VALID)
    # selection on validation only (protocol 11-12)
    val_mae = {}
    for tr in TRENDS:
        p = holt_winters(train, valid.index, tr)
        val_mae[str(tr)] = float(np.mean(np.abs(p - valid.to_numpy())))
    chosen = min(TRENDS, key=lambda t: (val_mae[str(t)], str(t)))
    val_pred = holt_winters(train, valid.index, chosen)
    resid = valid.to_numpy() - val_pred
    q = (float(np.quantile(resid, INTERVAL[0])), float(np.quantile(resid, INTERVAL[1])))
    # final: refit on train+validation, forecast holdout once
    hist = window(s, (TRAIN[0], VALID[1]))
    hold = window(s, HOLDOUT)
    base = weekday_mean(hist, hold.index)
    cand = holt_winters(hist, hold.index, chosen)
    df = pd.DataFrame({"gaming_date": hold.index.date, "actual": hold.to_numpy(),
                       "baseline_pred": base, "candidate_pred": cand,
                       "candidate_lo80": cand + q[0], "candidate_hi80": cand + q[1],
                       "horizon_days": np.arange(1, len(hold) + 1),
                       "weekday": hold.index.day_name().str[:3],
                       "is_event_day": [d in event_days for d in hold.index]})
    return ForecastRun(chosen, val_mae, q, df)


def event_counterfactuals(s: pd.Series, events: pd.DataFrame, trend: str | None,
                          event_days: set[pd.Timestamp]) -> pd.DataFrame:
    """Past-only counterfactual theo for each Fri-Sun day of each property promotion."""
    rows = []
    for e in events.itertuples():
        start, end = pd.Timestamp(e.start_date), pd.Timestamp(e.end_date)
        hist = s.loc[:start - pd.Timedelta(days=1)]
        dates = pd.date_range(start, end, freq="D")
        hw = holt_winters(hist, dates, trend)
        for i, d in enumerate(dates):
            if d.day_name()[:3] not in ("Fri", "Sat", "Sun"):
                continue
            prior = [d - pd.Timedelta(weeks=k) for k in range(1, 9)]
            same = [p for p in prior if p in hist.index and p not in event_days][:4]
            base = float(hist.loc[same].mean())
            rows.append({"event_id": e.event_id, "gaming_date": d.date(),
                         "weekday": d.day_name()[:3], "actual": float(s.loc[d]),
                         "baseline_counterfactual": base,
                         "candidate_counterfactual": float(hw[i]),
                         "issued_after": (start - pd.Timedelta(days=1)).date(),
                         "baseline_weeks_used": len(same)})
    df = pd.DataFrame(rows)
    df["baseline_excess"] = df.actual - df.baseline_counterfactual
    df["candidate_excess"] = df.actual - df.candidate_counterfactual
    return df
