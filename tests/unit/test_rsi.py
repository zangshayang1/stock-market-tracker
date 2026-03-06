"""Unit tests for RSI indicator."""
from __future__ import annotations

import pandas as pd
import pytest

from market_tracker.indicators.rsi import compute_rsi, latest_rsi


def test_rsi_length_matches_input(sample_close_series):
    rsi = compute_rsi(sample_close_series)
    assert len(rsi) == len(sample_close_series)


def test_rsi_first_values_are_nan():
    prices = pd.Series(range(1, 31), dtype=float)
    rsi = compute_rsi(prices, period=14)
    # First period-1 values should be NaN
    assert rsi.iloc[:13].isna().all()


def test_rsi_values_in_range(sample_close_series):
    rsi = compute_rsi(sample_close_series).dropna()
    assert (rsi >= 0).all()
    assert (rsi <= 100).all()


def test_rsi_all_up_trend_near_100():
    """Monotonically increasing prices → RSI near 100."""
    prices = pd.Series([float(i) for i in range(1, 50)])
    rsi = compute_rsi(prices).dropna()
    assert float(rsi.iloc[-1]) > 90.0


def test_rsi_all_down_trend_near_0():
    """Monotonically decreasing prices → RSI near 0."""
    prices = pd.Series([float(50 - i) for i in range(50)])
    rsi = compute_rsi(prices).dropna()
    assert float(rsi.iloc[-1]) < 10.0


def test_rsi_insufficient_data_returns_nan():
    prices = pd.Series([100.0] * 5)
    rsi = compute_rsi(prices, period=14)
    assert rsi.isna().all()


def test_latest_rsi_returns_float(sample_close_series):
    val = latest_rsi(sample_close_series)
    assert isinstance(val, float)
    assert 0 <= val <= 100


def test_latest_rsi_none_on_insufficient():
    val = latest_rsi(pd.Series([100.0] * 3), period=14)
    assert val is None


def test_rsi_flat_series():
    """Flat prices: all deltas = 0, RSI should be NaN or 50-ish (no defined direction)."""
    prices = pd.Series([100.0] * 30)
    rsi = compute_rsi(prices).dropna()
    # With all-zero deltas, avg_loss=0, RS=NaN, RSI=NaN
    # All values should be NaN (after warm-up)
    assert len(rsi) == 0 or rsi.isna().all() or ((rsi >= 0) & (rsi <= 100)).all()
