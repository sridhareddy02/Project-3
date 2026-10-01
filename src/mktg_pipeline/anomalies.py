"""Weekday-aware robust anomaly detection for daily marketing metrics.

Each day is compared with the median of the same weekday over the previous four weeks, on a log scale so that a 6x
spike and a drop to zero are both large and channels of different size are comparable. Noise is estimated with the
median absolute deviation of all residuals, which is not distorted by the anomalies being hunted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_THRESHOLD = 5.0
BASELINE_WEEKS = 4
MIN_SCALE = 0.02


def score_series(series: pd.Series, weeks: int = BASELINE_WEEKS) -> pd.DataFrame:
    """Return value, baseline and robust z-score per day. Days without a baseline or with a missing value get NaN."""
    s = series.astype(float).sort_index()
    logv = np.log1p(s)
    baseline = logv.groupby(logv.index.dayofweek).transform(lambda x: x.shift(1).rolling(weeks, min_periods=3).median())
    resid = logv - baseline
    centre = np.nanmedian(resid.to_numpy())
    mad = np.nanmedian(np.abs(resid.to_numpy() - centre))
    scale = max(1.4826 * mad, MIN_SCALE)
    z = (resid - centre) / scale
    return pd.DataFrame({"value": s, "baseline": np.expm1(baseline), "z": z})


def flag(scored: pd.DataFrame, threshold: float = DEFAULT_THRESHOLD) -> pd.Series:
    return scored["z"].abs() > threshold


def incidents(scored: pd.DataFrame, threshold: float = DEFAULT_THRESHOLD) -> pd.DataFrame:
    """Group consecutive flagged days into incidents."""
    flagged = flag(scored, threshold).fillna(False)
    rows, start, prev = [], None, None
    for day, is_flag in flagged.items():
        if is_flag and start is None:
            start = day
        if is_flag:
            prev = day
        if not is_flag and start is not None:
            rows.append((start, prev))
            start = None
    if start is not None:
        rows.append((start, prev))
    out = []
    for a, b in rows:
        part = scored.loc[a:b]
        peak = part["z"].abs().idxmax()
        out.append({"start": a, "end": b, "days": len(part), "peak_z": float(part.loc[peak, "z"]),
                    "value": float(part.loc[peak, "value"]), "expected": float(part.loc[peak, "baseline"]),
                    "direction": "spike" if part.loc[peak, "z"] > 0 else "drop"})
    if not out:
        return _empty_incidents().drop(columns=["channel", "metric"])
    return pd.DataFrame(out, columns=["start", "end", "days", "peak_z", "value", "expected", "direction"])


INCIDENT_COLUMNS = ["channel", "metric", "start", "end", "days", "peak_z", "value", "expected", "direction"]


def _empty_incidents() -> pd.DataFrame:
    """An empty incident table with proper dtypes so downstream formatting works on clean data."""
    return pd.DataFrame({
        "channel": pd.Series(dtype="object"), "metric": pd.Series(dtype="object"),
        "start": pd.Series(dtype="datetime64[ns]"), "end": pd.Series(dtype="datetime64[ns]"),
        "days": pd.Series(dtype="int64"), "peak_z": pd.Series(dtype="float64"), "value": pd.Series(dtype="float64"),
        "expected": pd.Series(dtype="float64"), "direction": pd.Series(dtype="object"),
    })


METRICS = {
    "spend": ("spend", lambda m: m["spend"], True),
    "sessions": ("sessions", lambda m: m["sessions"], False),
    "transactions": ("transactions", lambda m: m["transactions"], False),
    "conversion_rate": ("conversion_rate", lambda m: m["transactions"] / m["sessions"].where(m["sessions"] > 0), False),
}


def detect(mart: pd.DataFrame, threshold: float = DEFAULT_THRESHOLD) -> pd.DataFrame:
    """Scan every channel and metric in the daily mart. Returns one row per incident."""
    mart = mart.copy()
    mart["date"] = pd.to_datetime(mart["date"])
    frames = []
    for channel, part in mart.groupby("channel"):
        part = part.set_index("date").sort_index()
        for metric, (_, getter, paid_only) in METRICS.items():
            if paid_only and not bool(part["is_paid"].iloc[0]):
                continue
            series = getter(part)
            if series.notna().sum() < 28:
                continue
            inc = incidents(score_series(series), threshold)
            if len(inc):
                frames.append(inc.assign(channel=channel, metric=metric))
    if not frames:
        return _empty_incidents()
    out = pd.concat(frames, ignore_index=True)
    return out[["channel", "metric", "start", "end", "days", "peak_z", "value", "expected", "direction"]].sort_values(
        ["start", "channel", "metric"]).reset_index(drop=True)
