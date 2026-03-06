"""
Alarm deduplication state manager.

State is persisted to ~/.market-tracker/alarm_state.json with atomic
writes (tempfile → os.replace) to avoid corruption on SIGTERM.

3-layer dedup:
  1. Cooldown window  — suppress until cooldown_minutes elapsed
  2. Side tracking    — PriceThreshold with require_cross only fires on edge
  3. Silence command  — silenced_until timestamp per alarm
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_tracker.models import AllAlarmStates, AlarmState

logger = logging.getLogger(__name__)

DEFAULT_STATE_PATH = Path.home() / ".market-tracker" / "alarm_state.json"


class AlarmStateManager:
    """Load, query, and persist alarm dedup state."""

    def __init__(self, state_path: Path = DEFAULT_STATE_PATH) -> None:
        self.path = state_path
        self._data: AllAlarmStates = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_suppressed(self, alarm_name: str, cooldown_minutes: int) -> bool:
        """Return True if the alarm is in cooldown or silenced."""
        state = self._get(alarm_name)
        now = datetime.now(tz=timezone.utc)

        if state.silenced_until and now < state.silenced_until:
            logger.debug("%s silenced until %s", alarm_name, state.silenced_until)
            return True

        if state.last_fired:
            elapsed = now - state.last_fired
            if elapsed < timedelta(minutes=cooldown_minutes):
                remaining = timedelta(minutes=cooldown_minutes) - elapsed
                logger.debug(
                    "%s in cooldown — %s remaining",
                    alarm_name,
                    str(remaining).split(".")[0],
                )
                return True

        return False

    def get_last_side(self, alarm_name: str, rule_id: str) -> str | None:
        """Return the last known side for a PriceThreshold rule."""
        return self._get(alarm_name).last_side.get(rule_id)

    def record_fired(
        self,
        alarm_name: str,
        new_sides: dict[str, str | None] | None = None,
    ) -> None:
        """Mark alarm as fired now; optionally update side tracking."""
        state = self._get(alarm_name)
        state.last_fired = datetime.now(tz=timezone.utc)
        if new_sides:
            state.last_side.update(new_sides)
        self._save()

    def update_sides(self, alarm_name: str, new_sides: dict[str, str | None]) -> None:
        """Persist updated side tracking without recording a fire event."""
        state = self._get(alarm_name)
        state.last_side.update(new_sides)
        self._save()

    def silence(self, alarm_name: str, hours: float) -> datetime:
        """Silence an alarm for *hours* hours. Returns silenced_until timestamp."""
        state = self._get(alarm_name)
        silenced_until = datetime.now(tz=timezone.utc) + timedelta(hours=hours)
        state.silenced_until = silenced_until
        self._save()
        return silenced_until

    def get_all_states(self) -> dict[str, AlarmState]:
        return self._data.states

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, alarm_name: str) -> AlarmState:
        if alarm_name not in self._data.states:
            self._data.states[alarm_name] = AlarmState()
        return self._data.states[alarm_name]

    def _load(self) -> AllAlarmStates:
        if not self.path.exists():
            return AllAlarmStates()
        try:
            with self.path.open() as fh:
                raw = json.load(fh)
            return AllAlarmStates.model_validate(raw)
        except Exception as exc:
            logger.warning("Could not load state file %s: %s — starting fresh", self.path, exc)
            return AllAlarmStates()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._data.model_dump(mode="json")
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(payload, fh, indent=2, default=str)
            os.replace(tmp, self.path)
        except Exception:
            os.unlink(tmp)
            raise
