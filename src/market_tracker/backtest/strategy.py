"""
Strategy signal logic for the backtest engine.

Currently supports: dip_buy

Entry/exit signals receive the current bar's OHLCV row plus context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from market_tracker.models import BacktestConfig


@dataclass
class Position:
    """An open position."""
    symbol: str
    entry_date: str
    entry_price: float
    shares: int
    stop_loss_price: float


@dataclass
class Signal:
    action: str  # "buy" | "sell_all" | "none"
    reason: str = ""


def _pct_change(current: float, reference: float) -> float:
    if reference == 0:
        return 0.0
    return (current - reference) / reference * 100


class DipBuyStrategy:
    """
    Buy on dip (day_change_pct down), sell when target gain reached or stop-loss hit.
    """

    def __init__(self, cfg: BacktestConfig) -> None:
        p = cfg.strategy.params
        self.entry = p.entry_condition
        self.exit = p.exit_condition
        self.shares_per_trade = p.shares_per_trade
        self.max_open = p.max_open_positions
        self.stop_loss_pct = p.stop_loss_pct

    def entry_signal(
        self,
        row: pd.Series,
        prev_close: float,
    ) -> bool:
        """Return True if this bar triggers an entry."""
        cond = self.entry
        rule_type = cond.get("type", "day_change_pct")
        if rule_type == "day_change_pct":
            ref = prev_close if cond.get("reference", "prev_close") == "prev_close" else row["Open"]
            change = _pct_change(row["Close"], ref)
            direction = cond.get("direction", "down")
            threshold = float(cond.get("threshold_pct", 2.0))
            if direction == "down":
                return change <= -threshold
            return change >= threshold
        return False

    def exit_signal(
        self,
        row: pd.Series,
        position: Position,
    ) -> tuple[bool, str]:
        """Return (should_exit, reason)."""
        # Stop-loss check
        loss_pct = _pct_change(row["Close"], position.entry_price)
        if loss_pct <= -self.stop_loss_pct:
            return True, "stop_loss"

        # Target exit
        cond = self.exit
        rule_type = cond.get("type", "day_change_pct")
        if rule_type == "day_change_pct":
            ref_label = cond.get("reference", "entry_price")
            ref = position.entry_price if ref_label == "entry_price" else row["Open"]
            change = _pct_change(row["Close"], ref)
            direction = cond.get("direction", "up")
            threshold = float(cond.get("threshold_pct", 3.0))
            if direction == "up" and change >= threshold:
                return True, "target"
            if direction == "down" and change <= -threshold:
                return True, "target"

        return False, ""
