from __future__ import annotations

from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.errors import InvalidReminder

# Default: once a week on Sunday morning (user local time).
DEFAULT_WEIGHT_REMINDER_WEEKDAYS: frozenset[int] = frozenset({7})
DEFAULT_WEIGHT_REMINDER_TIME = time(9, 0)
DEFAULT_PROGRESS_PHOTO_REMINDER_WEEKDAYS: frozenset[int] = DEFAULT_WEIGHT_REMINDER_WEEKDAYS
DEFAULT_PROGRESS_PHOTO_REMINDER_TIME = DEFAULT_WEIGHT_REMINDER_TIME


def _validated_weekdays(weekdays: set[int] | frozenset[int] | list[int]) -> frozenset[int]:
    days = frozenset(int(day) for day in weekdays)
    if not days:
        raise InvalidReminder("reminder weekdays must not be empty")
    if any(day < 1 or day > 7 for day in days):
        raise InvalidReminder("weekday must be between 1 and 7")
    return days


class WeightReminder(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    user_id: UUID
    local_time: time
    weekdays: frozenset[int] = Field(default_factory=frozenset)
    last_sent_on: date | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        local_time: time,
        weekdays: set[int] | frozenset[int] | list[int],
    ) -> WeightReminder:
        return cls(user_id=user_id, local_time=local_time, weekdays=_validated_weekdays(weekdays))

    @classmethod
    def default_for_user(cls, *, user_id: UUID) -> WeightReminder:
        return cls.create(
            user_id=user_id,
            local_time=DEFAULT_WEIGHT_REMINDER_TIME,
            weekdays=DEFAULT_WEIGHT_REMINDER_WEEKDAYS,
        )

    def mark_sent(self, on: date) -> None:
        self.last_sent_on = on


class ProgressPhotoReminder(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    user_id: UUID
    local_time: time
    weekdays: frozenset[int] = Field(default_factory=frozenset)
    last_sent_on: date | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        local_time: time,
        weekdays: set[int] | frozenset[int] | list[int],
    ) -> ProgressPhotoReminder:
        return cls(user_id=user_id, local_time=local_time, weekdays=_validated_weekdays(weekdays))

    @classmethod
    def default_for_user(cls, *, user_id: UUID) -> ProgressPhotoReminder:
        return cls.create(
            user_id=user_id,
            local_time=DEFAULT_PROGRESS_PHOTO_REMINDER_TIME,
            weekdays=DEFAULT_PROGRESS_PHOTO_REMINDER_WEEKDAYS,
        )

    def mark_sent(self, on: date) -> None:
        self.last_sent_on = on
