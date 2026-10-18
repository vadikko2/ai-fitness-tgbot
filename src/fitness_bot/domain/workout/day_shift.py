"""Move one planned workout onto the next day, cascading through occupied days.

There is no separate "shift the week" operation in the program model. The
smallest correct version: walk forward from the skipped weekday and give each
occupied day the next weekday, until a rest day absorbs the chain. Titles,
positions and slots stay put — only ``weekday`` changes. A week with no rest
day cannot move (that would wrap onto itself); the caller leaves the plan as-is.
"""

from __future__ import annotations

from dataclasses import dataclass

from fitness_bot.domain.errors import CannotShiftTrainingDay, DomainError
from fitness_bot.domain.workout.document import WorkoutDay


@dataclass(frozen=True)
class DayShift:
    title: str
    from_weekday: int
    to_weekday: int


def _next_weekday(weekday: int) -> int:
    return 1 if weekday == 7 else weekday + 1


def shift_training_day_forward(days: list[WorkoutDay], weekday: int) -> tuple[list[WorkoutDay], list[DayShift]]:
    by_weekday = {day.weekday: day for day in days if day.weekday is not None}
    if weekday not in by_weekday:
        raise DomainError("weekday is not a training day")
    occupied = set(by_weekday)
    if len(occupied) >= 7:
        raise CannotShiftTrainingDay("no rest day left to shift the workout onto")

    landing = _next_weekday(weekday)
    guard = 0
    while landing in occupied:
        landing = _next_weekday(landing)
        guard += 1
        if guard > 7:
            raise CannotShiftTrainingDay("no rest day left to shift the workout onto")

    chain: list[int] = []
    cursor = weekday
    while cursor != landing:
        chain.append(cursor)
        cursor = _next_weekday(cursor)
        if len(chain) > 7:
            raise CannotShiftTrainingDay("no rest day left to shift the workout onto")

    moved_to = {old: _next_weekday(old) for old in chain}
    moves = [DayShift(title=by_weekday[old].title, from_weekday=old, to_weekday=moved_to[old]) for old in chain]
    new_days = [
        day.model_copy(update={"weekday": moved_to[day.weekday]}) if day.weekday in moved_to else day for day in days
    ]
    return new_days, moves
