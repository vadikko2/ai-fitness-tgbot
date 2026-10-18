from datetime import date

from fitness_bot.domain.errors import CannotShiftTrainingDay, DomainError
from fitness_bot.domain.workout.day_shift import shift_training_day_forward
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay
from fitness_bot.domain.workout.training_reminder import (
    evening_reminder_due,
    morning_reminder_due,
)


def _day(weekday: int, title: str) -> WorkoutDay:
    return WorkoutDay(
        weekday=weekday,
        title=title,
        position=weekday,
        slots=[
            ExerciseSlot(
                position=1,
                exercise_id=None,
                custom_request="жим",
                muscle_group="грудь",
                sets=3,
                reps=8,
                rest_seconds=60,
                rpe=7,
            )
        ],
    )


def test_shift_lands_on_the_next_rest_day() -> None:
    days, moves = shift_training_day_forward([_day(1, "Верх"), _day(3, "Низ"), _day(5, "Фул")], 1)
    assert [(day.weekday, day.title) for day in days] == [(2, "Верх"), (3, "Низ"), (5, "Фул")]
    assert [(move.from_weekday, move.to_weekday, move.title) for move in moves] == [(1, 2, "Верх")]


def test_shift_cascades_through_the_next_training_day() -> None:
    days, moves = shift_training_day_forward([_day(1, "Верх"), _day(2, "Ноги")], 1)
    assert [day.weekday for day in days] == [2, 3]
    assert [(move.from_weekday, move.to_weekday) for move in moves] == [(1, 2), (2, 3)]
    assert days[0].slots[0].custom_request == "жим"


def test_shift_wraps_sunday_onto_monday() -> None:
    days, moves = shift_training_day_forward([_day(7, "Воскр"), _day(1, "Пн")], 7)
    assert sorted(day.weekday for day in days) == [1, 2]
    assert [(move.from_weekday, move.to_weekday) for move in moves] == [(7, 1), (1, 2)]


def test_full_week_cannot_shift() -> None:
    days = [_day(weekday, f"День {weekday}") for weekday in range(1, 8)]
    try:
        shift_training_day_forward(days, 1)
    except CannotShiftTrainingDay:
        return
    raise AssertionError("expected CannotShiftTrainingDay")


def test_rest_weekday_is_not_shifted() -> None:
    try:
        shift_training_day_forward([_day(1, "Верх")], 2)
    except DomainError as exc:
        assert "not a training day" in str(exc)
        return
    raise AssertionError("expected DomainError")


def test_morning_window_stops_when_evening_starts() -> None:
    from datetime import datetime

    morning = datetime(2026, 10, 19, 9, 15)
    assert morning_reminder_due(morning, None)
    assert not morning_reminder_due(morning, date(2026, 10, 19))
    assert not morning_reminder_due(datetime(2026, 10, 19, 8, 59), None)
    assert not morning_reminder_due(datetime(2026, 10, 19, 20, 0), None)
    assert evening_reminder_due(datetime(2026, 10, 19, 20, 0), None)
    assert not evening_reminder_due(datetime(2026, 10, 19, 19, 59), None)
    assert not evening_reminder_due(datetime(2026, 10, 19, 21, 0), date(2026, 10, 19))
