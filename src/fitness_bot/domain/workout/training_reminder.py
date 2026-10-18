"""Prefs for the two fixed training nudges.

Times are not stored: evening is 20:00 local, morning is 09:00 local.
``user.timezone_offset`` is the clock (same as the rest of the bot). A missing
offset means UTC, matching ``local_calendar_date``.

Morning is due from 09:00 until 20:00. After 20:00 only the evening nudge
(about tomorrow) goes out, so a late restart does not send both on the same tick.
Each kind is sent at most once per local calendar day (``last_*_sent_on``).
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

TrainingReminderKind = Literal["evening", "morning"]

EVENING_LOCAL_TIME = time(20, 0)
MORNING_LOCAL_TIME = time(9, 0)


def local_clock_reached(local_dt: datetime, at: time) -> bool:
    return (local_dt.hour, local_dt.minute) >= (at.hour, at.minute)


def evening_reminder_due(local_dt: datetime, last_sent_on: date | None) -> bool:
    if last_sent_on == local_dt.date():
        return False
    return local_clock_reached(local_dt, EVENING_LOCAL_TIME)


def morning_reminder_due(local_dt: datetime, last_sent_on: date | None) -> bool:
    if last_sent_on == local_dt.date():
        return False
    if not local_clock_reached(local_dt, MORNING_LOCAL_TIME):
        return False
    return not local_clock_reached(local_dt, EVENING_LOCAL_TIME)


class TrainingReminderPrefs(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    user_id: UUID
    evening_enabled: bool = True
    morning_enabled: bool = True
    last_evening_sent_on: date | None = None
    last_morning_sent_on: date | None = None

    @classmethod
    def default_for_user(cls, *, user_id: UUID) -> TrainingReminderPrefs:
        return cls(user_id=user_id)

    def mark_sent(self, kind: TrainingReminderKind, on: date) -> None:
        if kind == "evening":
            self.last_evening_sent_on = on
        else:
            self.last_morning_sent_on = on

    def toggle(self, kind: TrainingReminderKind) -> None:
        if kind == "evening":
            self.evening_enabled = not self.evening_enabled
        else:
            self.morning_enabled = not self.morning_enabled

    def disable_all(self) -> None:
        self.evening_enabled = False
        self.morning_enabled = False
