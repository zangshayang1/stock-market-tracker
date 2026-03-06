"""
Alarm evaluator — runs all rules for an AlarmConfig and applies AND/OR logic.

Returns (triggered, triggered_rule_ids, messages).
Handles PriceThreshold side-tracking by passing/returning side state.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from market_tracker.models import AlarmConfig
from market_tracker.rules.factory import build_rule
from market_tracker.rules.price_rules import PriceThresholdRule

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    triggered: bool
    triggered_rule_ids: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    # rule_id → new side for PriceThreshold rules
    new_sides: dict[str, str | None] = field(default_factory=dict)


def evaluate_alarm(
    alarm: AlarmConfig,
    last_sides: dict[str, str | None] | None = None,
) -> EvalResult:
    """
    Evaluate all rules in *alarm*, applying alarm.logic (ANY | ALL).

    Parameters
    ----------
    alarm       : AlarmConfig
    last_sides  : mapping of rule_id → last known side (for PriceThreshold)
    """
    if last_sides is None:
        last_sides = {}

    results: list[tuple[bool, str]] = []
    new_sides: dict[str, str | None] = {}
    triggered_ids: list[str] = []
    messages: list[str] = []

    for rule_cfg in alarm.rules:
        rule = build_rule(rule_cfg)

        try:
            if isinstance(rule, PriceThresholdRule):
                fired, msg, new_side = rule.evaluate(last_side=last_sides.get(rule_cfg.id))
                new_sides[rule_cfg.id] = new_side
            else:
                fired, msg = rule.evaluate()

            results.append((fired, msg))
            messages.append(msg)
            if fired:
                triggered_ids.append(rule_cfg.id)

        except Exception as exc:
            logger.error(
                "Rule '%s' evaluation failed: %s", rule_cfg.id, exc, exc_info=True
            )
            results.append((False, f"ERROR in {rule_cfg.id}: {exc}"))
            messages.append(f"ERROR in {rule_cfg.id}: {exc}")

    # Apply logic gate
    if alarm.logic == "ANY":
        triggered = any(fired for fired, _ in results)
    else:  # ALL
        triggered = bool(results) and all(fired for fired, _ in results)

    if not triggered:
        triggered_ids = []  # clear partial list for ALL-logic partial fires

    return EvalResult(
        triggered=triggered,
        triggered_rule_ids=triggered_ids,
        messages=messages,
        new_sides=new_sides,
    )
