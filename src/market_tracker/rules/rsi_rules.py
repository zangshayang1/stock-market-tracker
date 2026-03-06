"""
RSI-based alarm rules.

params:
  condition : "overbought" | "oversold"
  threshold : float  (e.g. 70 for overbought, 30 for oversold)
  period    : int    (default 14)
"""
from __future__ import annotations

import logging

from market_tracker.data import cache
from market_tracker.indicators.rsi import latest_rsi
from market_tracker.models import RuleConfig
from market_tracker.rules.base import BaseRule

logger = logging.getLogger(__name__)


class RSIRule(BaseRule):
    """Fires when RSI is above (overbought) or below (oversold) threshold."""

    def __init__(self, config: RuleConfig) -> None:
        super().__init__(config)
        self.condition: str = self._require_param("condition")  # "overbought" | "oversold"
        self.threshold: float = float(self._require_param("threshold"))
        self.period: int = int(self.params.get("period", 14))

        if self.condition not in ("overbought", "oversold"):
            raise ValueError(
                f"RSIRule '{config.id}': condition must be 'overbought' or 'oversold', "
                f"got '{self.condition}'"
            )

    def evaluate(self) -> tuple[bool, str]:
        # Need enough bars for RSI warm-up: period + some buffer
        period_str = f"{self.period * 3}d"
        df = cache.get_history(self.symbol, period=period_str, interval="1d")

        if df.empty:
            return False, f"{self.symbol}: no history data"

        rsi_val = latest_rsi(df["Close"], period=self.period)
        if rsi_val is None:
            return False, f"{self.symbol}: insufficient data for RSI-{self.period}"

        if self.condition == "overbought":
            triggered = rsi_val >= self.threshold
        else:
            triggered = rsi_val <= self.threshold

        msg = (
            f"{self.symbol} RSI-{self.period}={rsi_val:.2f} "
            f"condition={self.condition} threshold={self.threshold}"
        )
        return triggered, msg
