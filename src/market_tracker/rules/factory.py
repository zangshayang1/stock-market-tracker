"""Rule factory: instantiate the correct rule class from a RuleConfig."""
from __future__ import annotations

from market_tracker.models import RuleConfig
from market_tracker.rules.base import BaseRule
from market_tracker.rules.price_rules import DayChangePctRule, NDayChangePctRule, PriceThresholdRule
from market_tracker.rules.rsi_rules import RSIRule
from market_tracker.rules.volume_rules import VolumeSpikeRule

_RULE_REGISTRY: dict[str, type[BaseRule]] = {
    "day_change_pct": DayChangePctRule,
    "nday_change_pct": NDayChangePctRule,
    "price_threshold": PriceThresholdRule,
    "rsi": RSIRule,
    "volume_spike": VolumeSpikeRule,
}


def build_rule(config: RuleConfig) -> BaseRule:
    """Return an instantiated rule for *config.type*."""
    cls = _RULE_REGISTRY.get(config.type)
    if cls is None:
        raise ValueError(f"Unknown rule type '{config.type}'")
    return cls(config)
