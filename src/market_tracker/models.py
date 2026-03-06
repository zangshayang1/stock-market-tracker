"""
Core domain models for market-tracker.

All Pydantic v2 models. These are the single source of truth for
data shapes passed between layers.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Rule models
# ---------------------------------------------------------------------------

class RuleConfig(BaseModel):
    """Configuration for a single alarm rule."""

    id: str
    type: Literal[
        "day_change_pct",
        "nday_change_pct",
        "price_threshold",
        "rsi",
        "volume_spike",
    ]
    symbol: str
    params: dict[str, Any] = Field(default_factory=dict)


class AlarmConfig(BaseModel):
    """Configuration for a named alarm (one or more rules + metadata)."""

    name: str
    cooldown_minutes: int = Field(default=60, ge=0)
    logic: Literal["ANY", "ALL"] = "ANY"
    rules: list[RuleConfig] = Field(min_length=1)


class AlarmsFile(BaseModel):
    """Top-level structure of alarms.yaml."""

    alarms: list[AlarmConfig]


# ---------------------------------------------------------------------------
# Alarm state / event models
# ---------------------------------------------------------------------------

class AlarmFiredEvent(BaseModel):
    """Record of a single alarm firing (written to log / SNS payload)."""

    alarm_name: str
    fired_at: datetime
    triggered_rules: list[str]  # rule IDs that triggered
    message: str


class AlarmState(BaseModel):
    """Persisted state for a single alarm (stored in alarm_state.json)."""

    last_fired: datetime | None = None
    silenced_until: datetime | None = None
    # price_threshold side tracking: rule_id → "above" | "below" | None
    last_side: dict[str, str | None] = Field(default_factory=dict)


class AllAlarmStates(BaseModel):
    """Root of alarm_state.json — maps alarm name → AlarmState."""

    states: dict[str, AlarmState] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Backtest models
# ---------------------------------------------------------------------------

class BacktestConfig(BaseModel):
    """Top-level backtest configuration."""

    symbol: str
    start_date: str  # "YYYY-MM-DD"
    end_date: str    # "YYYY-MM-DD"
    initial_capital: float = Field(default=10_000.0, gt=0)
    commission_per_trade: float = Field(default=1.0, ge=0)
    strategy: StrategyConfig


class StrategyConfig(BaseModel):
    """Strategy definition inside backtest config."""

    type: Literal["dip_buy"]
    params: DipBuyParams


class DipBuyParams(BaseModel):
    """Parameters for the dip_buy strategy."""

    entry_condition: dict[str, Any]
    shares_per_trade: int = Field(default=10, gt=0)
    exit_condition: dict[str, Any]
    max_open_positions: int = Field(default=5, gt=0)
    stop_loss_pct: float = Field(default=5.0, gt=0)


class BacktestConfigFile(BaseModel):
    """Top-level structure of backtest.yaml."""

    backtest: BacktestConfig


class TradeRecord(BaseModel):
    """A single completed trade."""

    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    shares: int
    pnl: float
    pnl_pct: float
    exit_reason: Literal["target", "stop_loss", "end_of_data"]


class BacktestResult(BaseModel):
    """Full output of a backtest run."""

    symbol: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return_pct: float
    max_drawdown_pct: float
    longest_drawdown_days: int
    win_rate_pct: float
    sharpe_ratio: float
    profit_factor: float
    avg_win_pct: float
    avg_loss_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    trades: list[TradeRecord]
