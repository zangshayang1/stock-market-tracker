"""Unit tests for alarm evaluator and state manager."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from market_tracker.alarms.evaluator import evaluate_alarm
from market_tracker.alarms.state import AlarmStateManager
from market_tracker.models import AlarmConfig, RuleConfig


# ---------------------------------------------------------------------------
# AlarmStateManager tests
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_state(tmp_path):
    return AlarmStateManager(state_path=tmp_path / "alarm_state.json")


class TestAlarmStateManager:
    def test_initial_not_suppressed(self, tmp_state):
        assert not tmp_state.is_suppressed("MyAlarm", cooldown_minutes=60)

    def test_suppressed_after_fire(self, tmp_state):
        tmp_state.record_fired("MyAlarm")
        assert tmp_state.is_suppressed("MyAlarm", cooldown_minutes=60)

    def test_not_suppressed_after_cooldown_elapsed(self, tmp_state):
        # Fire and set last_fired to 2 hours ago
        tmp_state.record_fired("MyAlarm")
        state = tmp_state._get("MyAlarm")
        state.last_fired = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        assert not tmp_state.is_suppressed("MyAlarm", cooldown_minutes=60)

    def test_silence_suppresses(self, tmp_state):
        until = tmp_state.silence("MyAlarm", hours=4.0)
        assert tmp_state.is_suppressed("MyAlarm", cooldown_minutes=0)
        assert until > datetime.now(tz=timezone.utc)

    def test_state_persisted_to_disk(self, tmp_path):
        path = tmp_path / "state.json"
        mgr = AlarmStateManager(state_path=path)
        mgr.record_fired("Alpha")
        # Re-load
        mgr2 = AlarmStateManager(state_path=path)
        assert mgr2.is_suppressed("Alpha", cooldown_minutes=120)

    def test_side_tracking(self, tmp_state):
        tmp_state.update_sides("MyAlarm", {"rule1": "above"})
        assert tmp_state.get_last_side("MyAlarm", "rule1") == "above"

    def test_atomic_write_on_corrupt_file(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("NOT JSON")
        # Should start fresh, not crash
        mgr = AlarmStateManager(state_path=path)
        assert mgr.get_all_states() == {}


# ---------------------------------------------------------------------------
# Evaluator tests
# ---------------------------------------------------------------------------

def make_alarm(logic="ANY"):
    return AlarmConfig(
        name="Test Alarm",
        cooldown_minutes=60,
        logic=logic,
        rules=[
            RuleConfig(id="r1", type="day_change_pct", symbol="AAPL",
                       params=dict(direction="down", threshold_pct=2.0, reference="prev_close")),
        ],
    )


class TestEvaluator:
    def test_any_logic_fires_on_one_rule(self):
        alarm = make_alarm("ANY")
        with patch("market_tracker.rules.price_rules.cache.get_quote",
                   return_value={"last_price": 97.0, "previous_close": 100.0, "open": 100.0}):
            result = evaluate_alarm(alarm)
        assert result.triggered
        assert "r1" in result.triggered_rule_ids

    def test_any_logic_no_fire_on_zero_rules(self):
        alarm = make_alarm("ANY")
        with patch("market_tracker.rules.price_rules.cache.get_quote",
                   return_value={"last_price": 99.0, "previous_close": 100.0, "open": 100.0}):
            result = evaluate_alarm(alarm)
        assert not result.triggered

    def test_all_logic_requires_all_rules(self):
        alarm = AlarmConfig(
            name="ALL Alarm",
            cooldown_minutes=60,
            logic="ALL",
            rules=[
                RuleConfig(id="r1", type="day_change_pct", symbol="AAPL",
                           params=dict(direction="down", threshold_pct=2.0, reference="prev_close")),
                RuleConfig(id="r2", type="day_change_pct", symbol="AAPL",
                           params=dict(direction="down", threshold_pct=1.0, reference="prev_close")),
            ],
        )
        # Both rules trigger (−3%)
        with patch("market_tracker.rules.price_rules.cache.get_quote",
                   return_value={"last_price": 97.0, "previous_close": 100.0, "open": 100.0}):
            result = evaluate_alarm(alarm)
        assert result.triggered

    def test_all_logic_partial_fire_not_triggered(self):
        alarm = AlarmConfig(
            name="ALL Alarm",
            cooldown_minutes=60,
            logic="ALL",
            rules=[
                RuleConfig(id="r1", type="day_change_pct", symbol="AAPL",
                           params=dict(direction="down", threshold_pct=2.0, reference="prev_close")),
                RuleConfig(id="r2", type="day_change_pct", symbol="AAPL",
                           params=dict(direction="down", threshold_pct=5.0, reference="prev_close")),
            ],
        )
        # Only r1 triggers (−3%), r2 doesn't (needs −5%)
        with patch("market_tracker.rules.price_rules.cache.get_quote",
                   return_value={"last_price": 97.0, "previous_close": 100.0, "open": 100.0}):
            result = evaluate_alarm(alarm)
        assert not result.triggered

    def test_rule_error_caught_gracefully(self):
        alarm = make_alarm("ANY")
        with patch("market_tracker.rules.price_rules.cache.get_quote", side_effect=RuntimeError("boom")):
            result = evaluate_alarm(alarm)
        # Should not crash; rule error → not triggered
        assert not result.triggered
        assert any("ERROR" in m for m in result.messages)
