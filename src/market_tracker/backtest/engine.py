"""
Event-driven daily-bar backtest engine.

Loop: for each bar in the historical OHLCV series —
  1. Check open positions for exit conditions (stop-loss or target)
  2. Check entry condition for new positions (if under max_open)
  3. Record equity snapshot

After loop: close all open positions at last price (end_of_data exit reason).
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from market_tracker.backtest.metrics import (
    max_drawdown,
    sharpe_ratio,
    total_return_pct,
    trade_stats,
)
from market_tracker.backtest.strategy import DipBuyStrategy, Position
from market_tracker.data.fetcher import fetch_history
from market_tracker.models import BacktestConfig, BacktestResult, TradeRecord

logger = logging.getLogger(__name__)


def run_backtest(cfg: BacktestConfig) -> BacktestResult:
    """Execute a full backtest and return results."""
    df = _load_data(cfg)
    if df.empty:
        raise ValueError(f"No data returned for {cfg.symbol} [{cfg.start_date}:{cfg.end_date}]")

    strategy = DipBuyStrategy(cfg)
    capital = cfg.initial_capital
    positions: list[Position] = []
    completed_trades: list[TradeRecord] = []
    equity_curve: list[float] = []
    daily_returns: list[float] = []
    prev_equity = capital

    for i, (idx, row) in enumerate(df.iterrows()):
        date_str = str(idx)[:10]
        prev_close = float(df["Close"].iloc[i - 1]) if i > 0 else float(row["Open"])

        # Check exits
        still_open: list[Position] = []
        for pos in positions:
            should_exit, reason = strategy.exit_signal(row, pos)
            if should_exit:
                exit_price = float(row["Close"])
                pnl = (exit_price - pos.entry_price) * pos.shares - cfg.commission_per_trade
                pnl_pct = (exit_price - pos.entry_price) / pos.entry_price * 100
                capital += exit_price * pos.shares - cfg.commission_per_trade
                completed_trades.append(TradeRecord(
                    symbol=cfg.symbol,
                    entry_date=pos.entry_date,
                    entry_price=pos.entry_price,
                    exit_date=date_str,
                    exit_price=exit_price,
                    shares=pos.shares,
                    pnl=round(pnl, 2),
                    pnl_pct=round(pnl_pct, 2),
                    exit_reason=reason,
                ))
            else:
                still_open.append(pos)
        positions = still_open

        # Check entry
        if (
            len(positions) < strategy.max_open
            and strategy.entry_signal(row, prev_close)
        ):
            cost = strategy.shares_per_trade * float(row["Close"]) + cfg.commission_per_trade
            if cost <= capital:
                capital -= cost
                stop_price = float(row["Close"]) * (1 - strategy.stop_loss_pct / 100)
                positions.append(Position(
                    symbol=cfg.symbol,
                    entry_date=date_str,
                    entry_price=float(row["Close"]),
                    shares=strategy.shares_per_trade,
                    stop_loss_price=stop_price,
                ))
            else:
                logger.warning(
                    "%s: insufficient capital ($%.2f) to open position (need $%.2f)",
                    date_str, capital, cost,
                )

        # Equity snapshot = cash + mark-to-market open positions
        open_value = sum(p.shares * float(row["Close"]) for p in positions)
        equity = capital + open_value
        equity_curve.append(equity)
        if prev_equity > 0:
            daily_returns.append((equity - prev_equity) / prev_equity)
        prev_equity = equity

    # Close remaining positions at last bar
    if positions and not df.empty:
        last_close = float(df["Close"].iloc[-1])
        last_date = str(df.index[-1])[:10]
        for pos in positions:
            pnl = (last_close - pos.entry_price) * pos.shares - cfg.commission_per_trade
            pnl_pct = (last_close - pos.entry_price) / pos.entry_price * 100
            capital += last_close * pos.shares - cfg.commission_per_trade
            completed_trades.append(TradeRecord(
                symbol=cfg.symbol,
                entry_date=pos.entry_date,
                entry_price=pos.entry_price,
                exit_date=last_date,
                exit_price=last_close,
                shares=pos.shares,
                pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 2),
                exit_reason="end_of_data",
            ))
        equity_curve[-1] = capital

    final_capital = equity_curve[-1] if equity_curve else cfg.initial_capital
    dd_pct, dd_days = max_drawdown(equity_curve)
    sr = sharpe_ratio(daily_returns)
    stats = trade_stats(completed_trades)

    return BacktestResult(
        symbol=cfg.symbol,
        start_date=cfg.start_date,
        end_date=cfg.end_date,
        initial_capital=cfg.initial_capital,
        final_capital=round(final_capital, 2),
        total_return_pct=round(total_return_pct(cfg.initial_capital, final_capital), 2),
        max_drawdown_pct=round(dd_pct, 2),
        longest_drawdown_days=dd_days,
        win_rate_pct=round(stats["win_rate_pct"], 1),
        sharpe_ratio=round(sr, 3),
        profit_factor=round(stats["profit_factor"], 2),
        avg_win_pct=round(stats["avg_win_pct"], 2),
        avg_loss_pct=round(stats["avg_loss_pct"], 2),
        total_trades=stats["total_trades"],
        winning_trades=stats["winning_trades"],
        losing_trades=stats["losing_trades"],
        trades=completed_trades,
    )


def _load_data(cfg: BacktestConfig) -> pd.DataFrame:
    """Fetch full OHLCV history for the backtest window."""
    df = fetch_history(
        cfg.symbol,
        period="max",
        interval="1d",
    )
    if df.empty:
        return df

    # Filter to requested date range
    df.index = pd.to_datetime(df.index)
    mask = (df.index >= cfg.start_date) & (df.index <= cfg.end_date)
    df = df.loc[mask].copy()
    return df
