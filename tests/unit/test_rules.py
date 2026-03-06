"""Unit tests for alarm rules (using mocked cache)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from market_tracker.models import RuleConfig
from market_tracker.rules.price_rules import DayChangePctRule, NDayChangePctRule, PriceThresholdRule
from market_tracker.rules.rsi_rules import RSIRule
from market_tracker.rules.volume_rules import VolumeSpikeRule


def make_cfg(rule_type: str, symbol: str = "AAPL", params: dict = None, rule_id: str = "r1"):
    return RuleConfig(id=rule_id, type=rule_type, symbol=symbol, params=params or {})


# ---------------------------------------------------------------------------
# DayChangePctRule
# ---------------------------------------------------------------------------

class TestDayChangePctRule:
    def _rule(self, direction="down", threshold=2.0, reference="prev_close"):
        cfg = make_cfg("day_change_pct", params=dict(
            direction=direction, threshold_pct=threshold, reference=reference
        ))
        return DayChangePctRule(cfg)

    def _mock_quote(self, last, prev_close=100.0, open_=100.0):
        return {"last_price": last, "previous_close": prev_close, "open": open_}

    def test_fires_on_2pct_drop(self):
        rule = self._rule()
        with patch("market_tracker.rules.price_rules.cache.get_quote", return_value=self._mock_quote(97.9)):
            fired, msg = rule.evaluate()
        assert fired

    def test_does_not_fire_on_1pct_drop(self):
        rule = self._rule()
        with patch("market_tracker.rules.price_rules.cache.get_quote", return_value=self._mock_quote(99.0)):
            fired, _ = rule.evaluate()
        assert not fired

    def test_fires_on_2pct_gain_direction_up(self):
        rule = self._rule(direction="up")
        with patch("market_tracker.rules.price_rules.cache.get_quote", return_value=self._mock_quote(102.1)):
            fired, _ = rule.evaluate()
        assert fired

    def test_no_quote_returns_false(self):
        rule = self._rule()
        with patch("market_tracker.rules.price_rules.cache.get_quote", return_value={}):
            fired, msg = rule.evaluate()
        assert not fired
        assert "no quote" in msg

    def test_open_reference(self):
        rule = self._rule(reference="open")
        quote = self._mock_quote(last=97.0, prev_close=100.0, open_=100.0)
        with patch("market_tracker.rules.price_rules.cache.get_quote", return_value=quote):
            fired, _ = rule.evaluate()
        assert fired  # 3% drop from open


# ---------------------------------------------------------------------------
# NDayChangePctRule
# ---------------------------------------------------------------------------

class TestNDayChangePctRule:
    def _rule(self, n_days=5, threshold=5.0, direction="down"):
        cfg = make_cfg("nday_change_pct", params=dict(
            direction=direction, threshold_pct=threshold, n_days=n_days
        ))
        return NDayChangePctRule(cfg)

    def _make_df(self, prices: list[float]) -> pd.DataFrame:
        return pd.DataFrame({"Close": prices})

    def test_fires_on_5day_drop(self):
        rule = self._rule()
        # Current = 90, 6 bars ago = 100 → −10% → fires at 5%
        df = self._make_df([100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 90.0])
        with patch("market_tracker.rules.price_rules.cache.get_history", return_value=df):
            fired, _ = rule.evaluate()
        assert fired

    def test_insufficient_history(self):
        rule = self._rule()
        df = self._make_df([100.0, 98.0])
        with patch("market_tracker.rules.price_rules.cache.get_history", return_value=df):
            fired, msg = rule.evaluate()
        assert not fired
        assert "insufficient" in msg

    def test_empty_df(self):
        rule = self._rule()
        with patch("market_tracker.rules.price_rules.cache.get_history", return_value=pd.DataFrame()):
            fired, _ = rule.evaluate()
        assert not fired


# ---------------------------------------------------------------------------
# PriceThresholdRule
# ---------------------------------------------------------------------------

class TestPriceThresholdRule:
    def _rule(self, direction="below", level=500.0, require_cross=True):
        cfg = make_cfg("price_threshold", params=dict(
            direction=direction, level=level, require_cross=require_cross
        ))
        return PriceThresholdRule(cfg)

    def test_crosses_below_fires(self):
        rule = self._rule(direction="below", level=500.0)
        with patch("market_tracker.rules.price_rules.cache.get_quote", return_value={"last_price": 498.0}):
            fired, _, new_side = rule.evaluate(last_side="above")
        assert fired
        assert new_side == "below"

    def test_already_below_no_cross(self):
        """require_cross=True: already below, no transition → no fire."""
        rule = self._rule(direction="below", level=500.0)
        with patch("market_tracker.rules.price_rules.cache.get_quote", return_value={"last_price": 498.0}):
            fired, _, _ = rule.evaluate(last_side="below")
        assert not fired

    def test_first_evaluation_no_fire(self):
        """require_cross=True: first time (last_side=None) → no fire."""
        rule = self._rule(direction="below", level=500.0)
        with patch("market_tracker.rules.price_rules.cache.get_quote", return_value={"last_price": 498.0}):
            fired, _, side = rule.evaluate(last_side=None)
        assert not fired
        assert side == "below"

    def test_require_cross_false_fires_while_below(self):
        rule = self._rule(require_cross=False)
        with patch("market_tracker.rules.price_rules.cache.get_quote", return_value={"last_price": 498.0}):
            fired, _, _ = rule.evaluate(last_side="below")
        assert fired


# ---------------------------------------------------------------------------
# RSIRule
# ---------------------------------------------------------------------------

class TestRSIRule:
    def _rule(self, condition="oversold", threshold=30.0):
        cfg = make_cfg("rsi", params=dict(condition=condition, threshold=threshold))
        return RSIRule(cfg)

    def _make_df(self, rsi_val: float) -> pd.DataFrame:
        """Return a price series that produces roughly the target RSI."""
        if rsi_val < 50:
            # Downtrend
            prices = [100.0 - i * 2 for i in range(50)]
        else:
            prices = [100.0 + i * 2 for i in range(50)]
        return pd.DataFrame({"Close": prices})

    def test_oversold_fires(self):
        rule = self._rule("oversold", 30.0)
        df = pd.DataFrame({"Close": [100.0 - i * 3 for i in range(50)]})
        with patch("market_tracker.rules.rsi_rules.cache.get_history", return_value=df):
            fired, msg = rule.evaluate()
        assert fired

    def test_overbought_fires(self):
        rule = self._rule("overbought", 70.0)
        # Strong monotonic uptrend → RSI near 100 (>70)
        df = pd.DataFrame({"Close": [100.0 + i * 2 for i in range(60)]})
        with patch("market_tracker.rules.rsi_rules.cache.get_history", return_value=df):
            fired, _ = rule.evaluate()
        assert fired

    def test_no_data_returns_false(self):
        rule = self._rule()
        with patch("market_tracker.rules.rsi_rules.cache.get_history", return_value=pd.DataFrame()):
            fired, msg = rule.evaluate()
        assert not fired

    def test_invalid_condition_raises(self):
        with pytest.raises(ValueError, match="condition must be"):
            RSIRule(make_cfg("rsi", params=dict(condition="neutral", threshold=50)))


# ---------------------------------------------------------------------------
# VolumeSpikeRule
# ---------------------------------------------------------------------------

class TestVolumeSpikeRule:
    def _rule(self, multiplier=3.0, min_time=None):
        p = dict(multiplier=multiplier)
        if min_time:
            p["min_time_of_day"] = min_time
        cfg = make_cfg("volume_spike", params=p)
        return VolumeSpikeRule(cfg)

    def _make_df(self, spike=True) -> pd.DataFrame:
        vols = [1_000_000.0] * 31
        if spike:
            vols[-1] = 5_000_000.0
        return pd.DataFrame({"Volume": vols})

    def test_spike_fires(self):
        rule = self._rule()
        df = self._make_df(spike=True)
        with patch("market_tracker.rules.volume_rules.cache.get_history", return_value=df):
            fired, _ = rule.evaluate()
        assert fired

    def test_no_spike(self):
        rule = self._rule()
        df = self._make_df(spike=False)
        with patch("market_tracker.rules.volume_rules.cache.get_history", return_value=df):
            fired, _ = rule.evaluate()
        assert not fired

    def test_min_time_suppresses_early(self, monkeypatch):
        """If current time is before min_time_of_day, should not fire."""
        from datetime import time as dtime
        from zoneinfo import ZoneInfo
        import datetime as dt_module

        rule = self._rule(min_time="11:00")
        # Mock datetime.now to return 9:30 ET
        fake_now = MagicMock(return_value=MagicMock(
            time=MagicMock(return_value=dtime(9, 30))
        ))
        with patch("market_tracker.rules.volume_rules.datetime") as mock_dt:
            mock_dt.now.return_value.time.return_value = dtime(9, 30)
            fired, msg = rule.evaluate()
        assert not fired
        assert "suppressed" in msg
