"""
Polling daemon — APScheduler BlockingScheduler.

Cycle (every `interval` seconds):
  1. Check NYSE market hours — skip if closed
  2. Batch-fetch data for all unique symbols (TTL cache prevents redundant calls)
  3. Evaluate all rules per alarm; apply AND/OR logic
  4. For triggered alarms: check dedup → send SNS → update state
  5. Log summary

Resilience: all errors caught; after 10 consecutive all-symbol failures,
            sends a health SNS alert.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import exchange_calendars as xcals
from apscheduler.schedulers.blocking import BlockingScheduler

from market_tracker.alarms.evaluator import evaluate_alarm
from market_tracker.alarms.state import AlarmStateManager
from market_tracker.alerts.sns import send_health_alert, send_sms
from market_tracker.config import load_alarms_config
from market_tracker.data import cache as data_cache
from market_tracker.models import AlarmFiredEvent

if TYPE_CHECKING:
    from market_tracker.models import AlarmsFile

logger = logging.getLogger(__name__)

PID_PATH = Path.home() / ".market-tracker" / "monitor.pid"
NYSE = xcals.get_calendar("XNYS")
CONSECUTIVE_FAILURE_LIMIT = 10


def _is_market_open() -> bool:
    """Return True if NYSE is currently open."""
    now = datetime.now(tz=NYSE.tz)
    try:
        return NYSE.is_open_on_minute(now)
    except Exception:
        return False


def _write_pid() -> None:
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()))


def _clear_pid() -> None:
    PID_PATH.unlink(missing_ok=True)


def _build_alarm_message(event: AlarmFiredEvent) -> str:
    rules_str = ", ".join(event.triggered_rules) if event.triggered_rules else "see details"
    return (
        f"[ALARM] {event.alarm_name}\n"
        f"Fired: {event.fired_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Rules: {rules_str}\n"
        f"{event.message}"
    )


class MonitorDaemon:
    def __init__(
        self,
        config_path: str,
        interval_seconds: int = 60,
        dry_run: bool = False,
    ) -> None:
        self.config_path = config_path
        self.interval = interval_seconds
        self.dry_run = dry_run
        self.state = AlarmStateManager()
        self._consecutive_failures = 0
        self._scheduler: BlockingScheduler | None = None

    def start(self) -> None:
        cfg = load_alarms_config(self.config_path)
        logger.info(
            "Starting monitor — %d alarms, %ds interval, dry_run=%s",
            len(cfg.alarms),
            self.interval,
            self.dry_run,
        )
        _write_pid()

        self._scheduler = BlockingScheduler(timezone="UTC")
        self._scheduler.add_job(
            self._poll_cycle,
            "interval",
            seconds=self.interval,
            id="poll",
            max_instances=1,
            args=[cfg],
        )

        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT, self._handle_sigterm)

        try:
            self._scheduler.start()
        finally:
            _clear_pid()

    def _handle_sigterm(self, signum, frame) -> None:
        logger.info("Received signal %d — shutting down", signum)
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
        _clear_pid()
        sys.exit(0)

    def _poll_cycle(self, cfg: "AlarmsFile") -> None:
        start_ts = datetime.now()

        if not _is_market_open():
            logger.debug("Market closed — skipping poll")
            return

        fired_count = 0
        eval_count = 0
        symbol_failures = 0

        for alarm in cfg.alarms:
            if self.state.is_suppressed(alarm.name, alarm.cooldown_minutes):
                continue

            # Build last_sides for PriceThreshold rules
            last_sides = {
                rule.id: self.state.get_last_side(alarm.name, rule.id)
                for rule in alarm.rules
            }

            try:
                result = evaluate_alarm(alarm, last_sides=last_sides)
                eval_count += len(alarm.rules)
            except Exception as exc:
                logger.error("Alarm '%s' evaluation error: %s", alarm.name, exc, exc_info=True)
                symbol_failures += 1
                continue

            # Always persist side updates even if not triggered
            if result.new_sides:
                self.state.update_sides(alarm.name, result.new_sides)

            if not result.triggered:
                continue

            event = AlarmFiredEvent(
                alarm_name=alarm.name,
                fired_at=datetime.utcnow().replace(tzinfo=None),
                triggered_rules=result.triggered_rule_ids,
                message="; ".join(result.messages[:3]),
            )
            msg = _build_alarm_message(event)

            if self.dry_run:
                logger.info("[DRY RUN] Would fire: %s", alarm.name)
                fired_count += 1
                continue

            sent = send_sms(msg)
            if sent:
                self.state.record_fired(alarm.name, new_sides=result.new_sides)
                fired_count += 1
                logger.info("Alarm fired: %s", alarm.name)
            else:
                logger.warning(
                    "Alarm '%s' triggered but SNS send failed — not updating state", alarm.name
                )

        elapsed_ms = int((datetime.now() - start_ts).total_seconds() * 1000)

        if symbol_failures > 0:
            self._consecutive_failures += 1
            if self._consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                logger.error("10 consecutive failure cycles — sending health alert")
                send_health_alert(
                    f"{self._consecutive_failures} consecutive poll failures. "
                    "Check network / yfinance."
                )
                self._consecutive_failures = 0
        else:
            self._consecutive_failures = 0

        logger.info(
            "Poll complete — %d rules evaluated, %d alarms fired, %dms",
            eval_count,
            fired_count,
            elapsed_ms,
        )
        # Flush data cache for next cycle
        data_cache.clear_cache()
