"""
yfinance wrapper — the ONLY place yfinance is imported in this codebase.

All callers receive a standardised pandas DataFrame with columns:
  Open, High, Low, Close, Volume  (adjusted, lowercase index = date/datetime)

Retry logic: exponential back-off on HTTP 429 (2s → 4s → 8s → 16s),
then raises after 4 attempts.
"""
from __future__ import annotations

import logging
import time
from typing import Literal

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Intervals supported for intraday vs daily fetches
Interval = Literal["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo"]

_RETRY_DELAYS = [2, 4, 8, 16]  # seconds


def fetch_history(
    symbol: str,
    period: str = "5d",
    interval: Interval = "1d",
    *,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """
    Fetch OHLCV history for *symbol*.

    Returns an empty DataFrame (not raises) on bad data so callers can
    gracefully skip symbols with data issues.
    """
    for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
        if delay:
            logger.warning("Retrying %s after %ds (attempt %d)", symbol, delay, attempt)
            time.sleep(delay)
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                period=period,
                interval=interval,
                auto_adjust=auto_adjust,
                raise_errors=True,
            )
            if df.empty:
                logger.warning("Empty DataFrame returned for %s", symbol)
                return pd.DataFrame()
            # Guard: drop rows where Close is 0 or NaN
            df = df[df["Close"].notna() & (df["Close"] > 0)]
            return df
        except Exception as exc:
            msg = str(exc).lower()
            if "429" in msg or "too many requests" in msg:
                if attempt <= len(_RETRY_DELAYS):
                    continue
            logger.error("Failed to fetch %s: %s", symbol, exc)
            return pd.DataFrame()
    return pd.DataFrame()


def fetch_quote(symbol: str) -> dict:
    """
    Return latest quote dict for *symbol* using ticker.info for accurate raw data.

    Fields returned:
      last_price      — regularMarketPrice (raw intraday last)
      previous_close  — regularMarketPreviousClose (unadjusted)
      open            — regularMarketOpen (unadjusted)
      day_high        — regularMarketDayHigh
      day_low         — regularMarketDayLow
      day_volume      — regularMarketVolume

    Returns empty dict on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return {
            "symbol": symbol,
            "last_price": info.get("regularMarketPrice"),
            "previous_close": info.get("regularMarketPreviousClose"),
            "open": info.get("regularMarketOpen"),
            "day_high": info.get("regularMarketDayHigh"),
            "day_low": info.get("regularMarketDayLow"),
            "day_volume": info.get("regularMarketVolume"),
        }
    except Exception as exc:
        logger.error("Failed to fetch quote for %s: %s", symbol, exc)
        return {}
