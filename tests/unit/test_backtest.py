"""Unit tests for backtesting metrics and engine."""
from __future__ import annotations

import pytest

from market_tracker.backtest.metrics import (
    max_drawdown,
    sharpe_ratio,
    total_return_pct,
    trade_stats,
)
from market_tracker.models import TradeRecord


# ---------------------------------------------------------------------------
# Metric tests
# ---------------------------------------------------------------------------

class TestTotalReturn:
    def test_gain(self):
        assert total_return_pct(10_000, 11_000) == pytest.approx(10.0)

    def test_loss(self):
        assert total_return_pct(10_000, 9_000) == pytest.approx(-10.0)

    def test_zero_initial(self):
        assert total_return_pct(0, 1000) == 0.0

    def test_break_even(self):
        assert total_return_pct(10_000, 10_000) == pytest.approx(0.0)


class TestMaxDrawdown:
    def test_no_drawdown(self):
        equity = [100.0, 110.0, 120.0, 130.0]
        dd, days = max_drawdown(equity)
        assert dd == pytest.approx(0.0, abs=1e-6)
        assert days == 0

    def test_simple_drawdown(self):
        # Peak 120 → trough 90 → drawdown = 25%
        equity = [100.0, 120.0, 100.0, 90.0, 95.0, 130.0]
        dd, days = max_drawdown(equity)
        assert dd == pytest.approx(25.0, rel=0.01)
        assert days >= 3

    def test_single_element(self):
        dd, days = max_drawdown([100.0])
        assert dd == 0.0
        assert days == 0

    def test_longest_drawdown_counted(self):
        # 5-bar drawdown
        equity = [100.0, 120.0, 115.0, 110.0, 105.0, 100.0, 95.0, 125.0]
        _, days = max_drawdown(equity)
        assert days >= 5


class TestSharpeRatio:
    def test_positive_returns_positive_sharpe(self):
        import numpy as np
        rng = np.random.default_rng(0)
        # Varied positive returns well above risk-free rate
        returns = list(0.005 + rng.normal(0, 0.002, 252))
        sr = sharpe_ratio(returns, risk_free_rate_annual=0.0)
        assert sr > 0

    def test_zero_std_returns_zero(self):
        returns = [0.0] * 100
        sr = sharpe_ratio(returns)
        assert sr == 0.0

    def test_insufficient_data(self):
        sr = sharpe_ratio([0.01])
        assert sr == 0.0

    def test_negative_returns_negative_sharpe(self):
        import numpy as np
        rng = np.random.default_rng(1)
        # Varied negative returns
        returns = list(-0.005 + rng.normal(0, 0.002, 252))
        sr = sharpe_ratio(returns, risk_free_rate_annual=0.0)
        assert sr < 0


class TestTradeStats:
    def _trade(self, pnl: float, pnl_pct: float) -> TradeRecord:
        return TradeRecord(
            symbol="AAPL",
            entry_date="2024-01-01",
            entry_price=100.0,
            exit_date="2024-01-10",
            exit_price=100.0 + pnl,
            shares=10,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason="target",
        )

    def test_empty_trades(self):
        stats = trade_stats([])
        assert stats["total_trades"] == 0
        assert stats["win_rate_pct"] == 0.0

    def test_all_wins(self):
        trades = [self._trade(10.0, 10.0) for _ in range(5)]
        stats = trade_stats(trades)
        assert stats["win_rate_pct"] == pytest.approx(100.0)
        assert stats["profit_factor"] == float("inf")

    def test_all_losses(self):
        trades = [self._trade(-10.0, -10.0) for _ in range(5)]
        stats = trade_stats(trades)
        assert stats["win_rate_pct"] == pytest.approx(0.0)
        assert stats["profit_factor"] == pytest.approx(0.0)

    def test_mixed(self):
        trades = [
            self._trade(20.0, 20.0),
            self._trade(20.0, 20.0),
            self._trade(-10.0, -10.0),
        ]
        stats = trade_stats(trades)
        assert stats["win_rate_pct"] == pytest.approx(200/3, rel=0.01)
        assert stats["profit_factor"] == pytest.approx(4.0)
        assert stats["avg_win_pct"] == pytest.approx(20.0)
        assert stats["avg_loss_pct"] == pytest.approx(-10.0)
