"""Shared pytest fixtures."""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def sample_close_series():
    """30 days of synthetic closing prices starting at 100."""
    import numpy as np
    rng = np.random.default_rng(42)
    prices = [100.0]
    for _ in range(29):
        prices.append(prices[-1] * (1 + rng.normal(0, 0.01)))
    return pd.Series(prices, name="Close")


@pytest.fixture
def flat_close_series():
    """Flat price series — RSI should be undefined / 50."""
    return pd.Series([100.0] * 30, name="Close")


@pytest.fixture
def sample_volume_series():
    """30 days of synthetic volume, last day is a spike."""
    vols = [1_000_000] * 30
    vols[-1] = 5_000_000  # 5× spike
    return pd.Series(vols, name="Volume", dtype=float)
