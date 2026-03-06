"""Unit tests for volume indicators."""
from __future__ import annotations

import pandas as pd
import pytest

from market_tracker.indicators.volume import (
    is_volume_spike,
    rolling_avg_volume,
    volume_spike_ratio,
)


def test_rolling_avg_volume_length(sample_volume_series):
    avg = rolling_avg_volume(sample_volume_series, window=10)
    assert len(avg) == len(sample_volume_series)


def test_rolling_avg_volume_first_window_nan(sample_volume_series):
    avg = rolling_avg_volume(sample_volume_series, window=10)
    assert avg.iloc[:9].isna().all()
    assert not pd.isna(avg.iloc[9])


def test_volume_spike_detected(sample_volume_series):
    # Last value is 5M, avg of first 29 is 1M → 5× spike
    assert is_volume_spike(sample_volume_series, multiplier=3.0, window=29)


def test_no_spike_below_multiplier():
    vols = pd.Series([1_000_000.0] * 31)
    vols.iloc[-1] = 1_500_000  # 1.5× — below 2× threshold
    assert not is_volume_spike(vols, multiplier=2.0, window=30)


def test_insufficient_data_returns_false():
    vols = pd.Series([1_000_000.0] * 5)
    assert not is_volume_spike(vols, multiplier=1.5, window=30)


def test_volume_spike_ratio(sample_volume_series):
    ratio = volume_spike_ratio(sample_volume_series, window=29)
    assert ratio is not None
    assert ratio == pytest.approx(5.0, rel=0.01)


def test_volume_spike_ratio_insufficient_returns_none():
    vols = pd.Series([1_000.0] * 5)
    assert volume_spike_ratio(vols, window=30) is None
