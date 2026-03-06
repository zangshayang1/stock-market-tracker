"""
Performance metrics for backtesting.

All metrics operate on a list of daily portfolio values (equity curve)
plus a list of completed TradeRecord objects.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from market_tracker.models import TradeRecord


def total_return_pct(initial: float, final: float) -> float:
    """(final - initial) / initial * 100"""
    if initial == 0:
        return 0.0
    return (final - initial) / initial * 100


def max_drawdown(equity_curve: list[float]) -> tuple[float, int]:
    """
    Return (max_drawdown_pct, longest_drawdown_days).

    max_drawdown_pct is a positive number (e.g. 20.5 means 20.5% drawdown).
    """
    if len(equity_curve) < 2:
        return 0.0, 0

    equity = np.array(equity_curve, dtype=float)
    running_max = np.maximum.accumulate(equity)
    drawdowns = (running_max - equity) / running_max * 100

    max_dd = float(np.max(drawdowns))

    # Longest consecutive period below running high
    in_drawdown = drawdowns > 0
    longest = 0
    current = 0
    for flag in in_drawdown:
        if flag:
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    return max_dd, longest


def sharpe_ratio(
    daily_returns: list[float],
    risk_free_rate_annual: float = 0.0425,
    trading_days: int = 252,
) -> float:
    """
    Annualized Sharpe ratio.

    daily_returns : list of daily % returns (e.g. 0.01 = 1%)
    """
    if len(daily_returns) < 2:
        return 0.0

    arr = np.array(daily_returns, dtype=float)
    rfr_daily = (1 + risk_free_rate_annual) ** (1 / trading_days) - 1
    excess = arr - rfr_daily

    std = float(np.std(excess, ddof=1))
    if std == 0:
        return 0.0

    return float(np.mean(excess) / std * math.sqrt(trading_days))


def trade_stats(trades: list[TradeRecord]) -> dict:
    """
    Compute win rate, profit factor, avg win/loss from closed trades.

    Returns dict with keys:
      win_rate_pct, profit_factor, avg_win_pct, avg_loss_pct,
      winning_trades, losing_trades, total_trades
    """
    if not trades:
        return {
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_trades": 0,
        }

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]

    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))

    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    avg_win = (sum(t.pnl_pct for t in wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(t.pnl_pct for t in losses) / len(losses)) if losses else 0.0

    return {
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "total_trades": len(trades),
    }
