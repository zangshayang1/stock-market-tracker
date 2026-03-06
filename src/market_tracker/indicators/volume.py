"""
Volume indicators: rolling average volume and spike detection.
"""
from __future__ import annotations

import pandas as pd


def rolling_avg_volume(volume: pd.Series, window: int = 30) -> pd.Series:
    """
    Return a Series of rolling mean volumes over *window* trading days.

    The first window-1 values are NaN.
    """
    return volume.rolling(window=window, min_periods=window).mean()


def is_volume_spike(
    volume: pd.Series,
    multiplier: float = 2.0,
    window: int = 30,
) -> bool:
    """
    Return True if today's volume is >= *multiplier* × 30-day average.

    Requires at least *window* + 1 observations (window for avg, +1 for today).
    Returns False if insufficient data.
    """
    if len(volume) < window + 1:
        return False

    avg = rolling_avg_volume(volume.iloc[:-1], window=window)
    last_avg = avg.dropna()
    if last_avg.empty:
        return False

    today_volume = float(volume.iloc[-1])
    baseline = float(last_avg.iloc[-1])
    if baseline <= 0:
        return False

    return today_volume >= multiplier * baseline


def volume_spike_ratio(volume: pd.Series, window: int = 30) -> float | None:
    """
    Return today's volume / 30-day average, or None if insufficient data.
    Useful for logging / alert messages.
    """
    if len(volume) < window + 1:
        return None

    avg = rolling_avg_volume(volume.iloc[:-1], window=window)
    last_avg = avg.dropna()
    if last_avg.empty:
        return None

    baseline = float(last_avg.iloc[-1])
    if baseline <= 0:
        return None

    return float(volume.iloc[-1]) / baseline
