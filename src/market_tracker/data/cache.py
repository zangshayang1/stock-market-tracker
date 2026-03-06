"""
TTLCache keyed by (symbol, interval) with a 55-second TTL.

Prevents redundant yfinance calls when multiple rules reference the same symbol
within a single polling cycle.
"""
from __future__ import annotations

import logging
from typing import Callable

import pandas as pd
from cachetools import TTLCache, cached
from cachetools.keys import hashkey

logger = logging.getLogger(__name__)

# 55s TTL so data refreshes every poll cycle (default 60s interval)
_CACHE: TTLCache = TTLCache(maxsize=256, ttl=55)


def get_history(
    symbol: str,
    period: str = "5d",
    interval: str = "1d",
    fetch_fn: Callable[..., pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """
    Return cached history for (symbol, period, interval).

    *fetch_fn* defaults to the real fetcher but can be injected for tests.
    """
    from market_tracker.data.fetcher import fetch_history

    fn = fetch_fn or fetch_history
    key = hashkey(symbol, period, interval)
    if key in _CACHE:
        logger.debug("Cache hit for %s/%s/%s", symbol, period, interval)
        return _CACHE[key]

    df = fn(symbol, period=period, interval=interval)
    if not df.empty:
        _CACHE[key] = df
    return df


def get_quote(
    symbol: str,
    fetch_fn: Callable[..., dict] | None = None,
) -> dict:
    """
    Return cached fast_info quote for *symbol*.
    Quotes use a separate key space with the same TTL.
    """
    from market_tracker.data.fetcher import fetch_quote

    fn = fetch_fn or fetch_quote
    key = hashkey("quote", symbol)
    if key in _CACHE:
        logger.debug("Cache hit for quote/%s", symbol)
        return _CACHE[key]

    q = fn(symbol)
    if q:
        _CACHE[key] = q
    return q


def clear_cache() -> None:
    """Flush the entire cache (useful in tests)."""
    _CACHE.clear()
