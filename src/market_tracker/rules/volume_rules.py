"""
Volume spike alarm rule.

params:
  multiplier      : float  (e.g. 3.0 = today's volume ≥ 3× 30-day avg)
  window          : int    (default 30)
  min_time_of_day : str    (optional, "HH:MM" ET — don't fire before this time)
"""
from __future__ import annotations

import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from market_tracker.data import cache
from market_tracker.indicators.volume import is_volume_spike, volume_spike_ratio
from market_tracker.models import RuleConfig
from market_tracker.rules.base import BaseRule

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


class VolumeSpikeRule(BaseRule):
    """Fires when today's volume ≥ multiplier × N-day average volume."""

    def __init__(self, config: RuleConfig) -> None:
        super().__init__(config)
        self.multiplier: float = float(self._require_param("multiplier"))
        self.window: int = int(self.params.get("window", 30))
        min_tod = self.params.get("min_time_of_day")
        self.min_time: time | None = (
            datetime.strptime(min_tod, "%H:%M").time() if min_tod else None
        )

    def evaluate(self) -> tuple[bool, str]:
        # Check time-of-day gate
        if self.min_time is not None:
            now_et = datetime.now(tz=ET).time()
            if now_et < self.min_time:
                return False, (
                    f"{self.symbol}: volume rule suppressed before "
                    f"{self.min_time.strftime('%H:%M')} ET"
                )

        period = f"{self.window + 10}d"  # buffer for weekends
        df = cache.get_history(self.symbol, period=period, interval="1d")

        if df.empty or len(df) < self.window + 1:
            return False, f"{self.symbol}: insufficient volume history ({len(df)} bars)"

        triggered = is_volume_spike(df["Volume"], multiplier=self.multiplier, window=self.window)
        ratio = volume_spike_ratio(df["Volume"], window=self.window)
        ratio_str = f"{ratio:.2f}x" if ratio is not None else "N/A"

        msg = (
            f"{self.symbol} volume_ratio={ratio_str} "
            f"(threshold={self.multiplier:.1f}x, window={self.window}d)"
        )
        return triggered, msg
