from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from fitness_bot.domain.enums import SessionStatus
from fitness_bot.domain.users.user import local_calendar_date
from fitness_bot.domain.workout.document import WorkoutDay
from fitness_bot.domain.workout.program import Program
from fitness_bot.domain.workout.session import Session


@dataclass(frozen=True)
class TrainingWeekProgress:
    week_started_on: date | None
    planned_weekdays: list[int]
    completed_weekdays: list[int]
    week_finished: bool


def training_week_progress(
    program: Program,
    sessions: Sequence[Session],
    *,
    timezone_offset: str | None,
    now: datetime | None = None,
) -> TrainingWeekProgress:
    """UX microcycle status from program activation and completed sessions.

    ``now`` is reserved for callers that need a consistent clock; week bounds
    are derived from ``program.activated_at`` and each session's ``completed_at``.
    """
    _ = now
    planned = sorted(
        {day.weekday for day in program.days if day.weekday is not None},
    )
    if program.activated_at is None:
        return TrainingWeekProgress(
            week_started_on=None,
            planned_weekdays=planned,
            completed_weekdays=[],
            week_finished=False,
        )

    activated_at = program.activated_at
    if activated_at.tzinfo is None:
        activated_at = activated_at.replace(tzinfo=UTC)
    week_started_on = local_calendar_date(
        now=activated_at,
        timezone_offset=timezone_offset,
    )
    completed: set[int] = set()
    for session in sessions:
        if session.status != SessionStatus.COMPLETED or session.completed_at is None:
            continue
        completed_at = session.completed_at
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=UTC)
        if completed_at < activated_at:
            continue
        # A program day done on another calendar day (e.g. on a rest day) still counts as that day.
        completed.add(
            session.day.weekday or local_calendar_date(now=completed_at, timezone_offset=timezone_offset).isoweekday(),
        )

    completed_weekdays = sorted(completed)
    week_finished = bool(planned) and all(day in completed for day in planned)
    return TrainingWeekProgress(
        week_started_on=week_started_on,
        planned_weekdays=planned,
        completed_weekdays=completed_weekdays,
        week_finished=week_finished,
    )


def nearest_open_training_day(
    program: Program,
    completed_weekdays: Sequence[int],
    *,
    today_weekday: int,
    exclude_weekdays: Sequence[int] = (),
) -> WorkoutDay | None:
    """Next program day (cyclically from today) that is not completed in the current microcycle."""
    skipped = set(completed_weekdays) | set(exclude_weekdays)
    candidates = [day for day in program.days if day.weekday is not None and day.weekday not in skipped]
    if not candidates:
        return None
    return min(candidates, key=lambda day: ((day.weekday or 0) - today_weekday) % 7)
