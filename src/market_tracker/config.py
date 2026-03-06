"""
YAML config loading with Pydantic v2 validation.

Usage:
    alarms = load_alarms_config("configs/alarms.yaml")
    bt = load_backtest_config("configs/backtest.yaml")
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from market_tracker.models import AlarmsFile, BacktestConfigFile


def load_alarms_config(path: str | Path) -> AlarmsFile:
    """Load and validate alarms YAML. Raises ValueError on bad config."""
    raw = _load_yaml(path)
    try:
        return AlarmsFile.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid alarms config at {path}:\n{exc}") from exc


def load_backtest_config(path: str | Path) -> BacktestConfigFile:
    """Load and validate backtest YAML. Raises ValueError on bad config."""
    raw = _load_yaml(path)
    try:
        return BacktestConfigFile.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid backtest config at {path}:\n{exc}") from exc


def _load_yaml(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with p.open() as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping at top level in {path}")
    return data
