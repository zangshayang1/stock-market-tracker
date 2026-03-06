"""
Wilder's RSI using SMMA (Smoothed Moving Average) in pure pandas.

References: Wilder (1978). No TA-Lib dependency.
"""
from __future__ import annotations

import pandas as pd


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Return a Series of RSI values (0–100) aligned with *close*.

    Uses Wilder's SMMA (equivalent to EWM with alpha=1/period, adjust=False).
    The first *period* values are NaN.

    Parameters
    ----------
    close : pd.Series
        Adjusted closing prices, oldest first.
    period : int
        Lookback window (default 14).
    """
    if len(close) < period + 1:
        return pd.Series([float("nan")] * len(close), index=close.index)

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    # Wilder's smoothing: alpha = 1/period, adjust=False
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    # When avg_loss = 0 and avg_gain > 0, RSI = 100
    # When both are 0 (flat), RSI = NaN (undefined)
    rs = avg_gain / avg_loss.where(avg_loss != 0, other=float("nan"))
    rsi = 100 - (100 / (1 + rs))

    # Fill RSI=100 where avg_loss=0 but avg_gain > 0
    zero_loss_positive_gain = (avg_loss == 0) & (avg_gain > 0)
    rsi = rsi.where(~zero_loss_positive_gain, other=100.0)

    # First period-1 values are not meaningful (warm-up artefact)
    rsi.iloc[: period - 1] = float("nan")

    return rsi


def latest_rsi(close: pd.Series, period: int = 14) -> float | None:
    """Return the most recent RSI value, or None if insufficient data."""
    rsi = compute_rsi(close, period)
    last = rsi.dropna()
    if last.empty:
        return None
    return float(last.iloc[-1])
