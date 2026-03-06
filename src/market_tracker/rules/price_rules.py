"""
Price-based alarm rules:
  - day_change_pct  : intraday % change vs open or prev_close
  - nday_change_pct : % change over N trading days
  - price_threshold : price crosses above/below a fixed level
"""
from __future__ import annotations

import logging

from market_tracker.data import cache
from market_tracker.models import RuleConfig
from market_tracker.rules.base import BaseRule

logger = logging.getLogger(__name__)


class DayChangePctRule(BaseRule):
    """
    Fires when today's % change from reference exceeds threshold.

    params:
      direction     : "up" | "down"
      threshold_pct : float  (positive number, e.g. 2.0 = 2%)
      reference     : "open" | "prev_close"
    """

    def __init__(self, config: RuleConfig) -> None:
        super().__init__(config)
        self.direction: str = self._require_param("direction")
        self.threshold_pct: float = float(self._require_param("threshold_pct"))
        self.reference: str = self.params.get("reference", "prev_close")

    def evaluate(self) -> tuple[bool, str]:
        quote = cache.get_quote(self.symbol)
        if not quote:
            return False, f"{self.symbol}: no quote data"

        last = quote.get("last_price")
        ref_price = quote.get("open") if self.reference == "open" else quote.get("previous_close")

        if not last or not ref_price or ref_price == 0:
            return False, f"{self.symbol}: missing price data"

        change_pct = (last - ref_price) / ref_price * 100

        if self.direction == "down":
            triggered = change_pct <= -self.threshold_pct
        else:
            triggered = change_pct >= self.threshold_pct

        msg = (
            f"{self.symbol} day_change_pct={change_pct:.2f}% "
            f"(ref={self.reference}, threshold={self.threshold_pct:.2f}%, "
            f"direction={self.direction})"
        )
        return triggered, msg


class NDayChangePctRule(BaseRule):
    """
    Fires when % change over N trading days exceeds threshold.

    params:
      direction     : "up" | "down"
      threshold_pct : float
      n_days        : int  (e.g. 5)
    """

    def __init__(self, config: RuleConfig) -> None:
        super().__init__(config)
        self.direction: str = self._require_param("direction")
        self.threshold_pct: float = float(self._require_param("threshold_pct"))
        self.n_days: int = int(self._require_param("n_days"))

    def evaluate(self) -> tuple[bool, str]:
        # Need n_days+1 bars: today + n_days of history
        period = f"{self.n_days + 5}d"  # buffer for weekends/holidays
        df = cache.get_history(self.symbol, period=period, interval="1d")

        if df.empty or len(df) < self.n_days + 1:
            return False, f"{self.symbol}: insufficient history ({len(df)} bars)"

        current_close = float(df["Close"].iloc[-1])
        past_close = float(df["Close"].iloc[-(self.n_days + 1)])

        if past_close == 0:
            return False, f"{self.symbol}: past close is zero"

        change_pct = (current_close - past_close) / past_close * 100

        if self.direction == "down":
            triggered = change_pct <= -self.threshold_pct
        else:
            triggered = change_pct >= self.threshold_pct

        msg = (
            f"{self.symbol} {self.n_days}d_change_pct={change_pct:.2f}% "
            f"(threshold={self.threshold_pct:.2f}%, direction={self.direction})"
        )
        return triggered, msg


class PriceThresholdRule(BaseRule):
    """
    Fires when price crosses above/below a fixed level.

    params:
      direction     : "above" | "below"
      level         : float
      require_cross : bool  (default True — only fire on edge, not while above/below)

    Side-tracking state is managed externally by AlarmState (last_side).
    When require_cross=True, the evaluator passes last_side in; we update it.
    """

    def __init__(self, config: RuleConfig) -> None:
        super().__init__(config)
        self.direction: str = self._require_param("direction")
        self.level: float = float(self._require_param("level"))
        self.require_cross: bool = bool(self.params.get("require_cross", True))

    def evaluate(
        self,
        last_side: str | None = None,
    ) -> tuple[bool, str, str | None]:
        """
        Returns (triggered, message, new_side).

        new_side is the current side ("above" | "below") for state persistence.
        """
        quote = cache.get_quote(self.symbol)
        if not quote:
            return False, f"{self.symbol}: no quote data", last_side

        last = quote.get("last_price")
        if not last:
            return False, f"{self.symbol}: missing price", last_side

        current_side = "above" if last >= self.level else "below"

        if self.require_cross:
            # Only trigger on a transition
            if last_side is None:
                # First evaluation — record side, don't fire
                triggered = False
            else:
                triggered = current_side == self.direction and last_side != self.direction
        else:
            triggered = current_side == self.direction

        msg = (
            f"{self.symbol} price={last:.2f} level={self.level:.2f} "
            f"current_side={current_side} direction={self.direction}"
        )
        return triggered, msg, current_side
