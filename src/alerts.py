"""
alerts.py - Suppress repeated announcements when nothing meaningful changed.
"""

from __future__ import annotations

import time
from typing import Optional


PRIORITY_ORDER = {
    "critical": 0,
    "warning": 1,
    "info": 2,
}


class AlertSuppressor:
    def __init__(
        self,
        min_repeat_gap_sec: float = 8.0,
        force_repeat_after_sec: float = 18.0,
        distance_change_cm: float = 35.0,
    ):
        self.min_repeat_gap_sec = min_repeat_gap_sec
        self.force_repeat_after_sec = force_repeat_after_sec
        self.distance_change_cm = distance_change_cm
        self.reset()

    def reset(self):
        self.last_key = None
        self.last_time = 0.0
        self.last_distance_cm = None
        self.last_urgency = None

    def should_emit(
        self,
        key: str,
        urgency: str,
        distance_cm: Optional[float] = None,
        now: Optional[float] = None,
    ) -> bool:
        now = now or time.time()

        if not key:
            return True

        if self.last_key is None:
            self._remember(key, urgency, distance_cm, now)
            return True

        last_pri = PRIORITY_ORDER.get(self.last_urgency, 99)
        cur_pri = PRIORITY_ORDER.get(urgency, 99)
        is_upgrade = cur_pri < last_pri
        is_new_key = key != self.last_key

        if is_new_key or is_upgrade:
            self._remember(key, urgency, distance_cm, now)
            return True

        elapsed = now - self.last_time
        if elapsed < self.min_repeat_gap_sec:
            return False

        if (
            distance_cm is not None
            and self.last_distance_cm is not None
            and abs(distance_cm - self.last_distance_cm) >= self.distance_change_cm
        ):
            self._remember(key, urgency, distance_cm, now)
            return True

        if elapsed >= self.force_repeat_after_sec:
            self._remember(key, urgency, distance_cm, now)
            return True

        return False

    def _remember(self, key: str, urgency: str, distance_cm: Optional[float], now: float):
        self.last_key = key
        self.last_time = now
        self.last_distance_cm = distance_cm
        self.last_urgency = urgency
