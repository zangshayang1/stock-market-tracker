"""
Abstract base class for all alarm rules.

Every rule takes a RuleConfig and produces (triggered: bool, message: str).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from market_tracker.models import RuleConfig


class BaseRule(ABC):
    """Abstract base for all rule implementations."""

    def __init__(self, config: RuleConfig) -> None:
        self.config = config
        self.symbol = config.symbol
        self.params = config.params

    @abstractmethod
    def evaluate(self) -> tuple[bool, str]:
        """
        Evaluate this rule against current market data.

        Returns
        -------
        (triggered, message)
            triggered : bool — True if the rule condition is met
            message   : str  — human-readable description of the result
        """

    def _require_param(self, key: str):
        """Raise ValueError if a required param is missing."""
        if key not in self.params:
            raise ValueError(
                f"Rule '{self.config.id}' of type '{self.config.type}' "
                f"is missing required param '{key}'"
            )
        return self.params[key]
