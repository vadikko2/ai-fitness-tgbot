from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fitness_bot.domain.enums import ProgramStatus, ProgramType
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay
from fitness_bot.domain.workout.program import Program
from fitness_bot.domain.workout.session import Session
from fitness_bot.domain.workout.week_progress import nearest_open_training_day, training_week_progress


def _slot() -> ExerciseSlot:
    return ExerciseSlot(
        position=1,
        exercise_id=uuid4(),
        sets=3,
        reps=8,
        rest_seconds=90,
        rpe=7,
    )


def _program(*, weekdays: list[int], activated_at: datetime) -> Program:
    return Program(
        user_id=uuid4(),
        program_type=ProgramType.FULL_BODY,
        status=ProgramStatus.ACTIVE,
        days=[
            WorkoutDay(weekday=day, title=f"День {i}", position=i, slots=[_slot()])
            for i, day in enumerate(weekdays, start=1)
        ],
        activated_at=activated_at,
    )


def _completed_session(*, user_id, weekday: int | None, completed_at: datetime) -> Session:
    session = Session.from_template_day(
        user_id=user_id,
        program_type=ProgramType.FULL_BODY,
        day=WorkoutDay(weekday=weekday, title="Done", position=1, slots=[_slot()]),
        now=completed_at,
    )
    session.finalize(now=completed_at)
    return session


def test_week_progress_not_finished_until_all_planned_days() -> None:
    activated = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)  # Monday local +03 → still Mon
    program = _program(weekdays=[1, 3, 5], activated_at=activated)
    user_id = program.user_id
    sessions = [
        _completed_session(
            user_id=user_id,
            weekday=1,
            completed_at=activated + timedelta(hours=2),
        ),
        _completed_session(
            user_id=user_id,
            weekday=3,
            completed_at=activated + timedelta(days=2),
        ),
    ]
    progress = training_week_progress(program, sessions, timezone_offset="+03:00")
    assert progress.week_started_on is not None
    assert progress.planned_weekdays == [1, 3, 5]
    assert progress.completed_weekdays == [1, 3]
    assert progress.week_finished is False


def test_week_progress_finished_when_all_planned_covered() -> None:
    activated = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)
    program = _program(weekdays=[1, 3, 5], activated_at=activated)
    user_id = program.user_id
    sessions = [
        _completed_session(user_id=user_id, weekday=1, completed_at=activated + timedelta(hours=1)),
        _completed_session(user_id=user_id, weekday=3, completed_at=activated + timedelta(days=2)),
        _completed_session(user_id=user_id, weekday=5, completed_at=activated + timedelta(days=4)),
    ]
    progress = training_week_progress(program, sessions, timezone_offset="+03:00")
    assert progress.completed_weekdays == [1, 3, 5]
    assert progress.week_finished is True


def test_week_progress_ignores_sessions_before_activation() -> None:
    activated = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)
    program = _program(weekdays=[1, 3], activated_at=activated)
    user_id = program.user_id
    sessions = [
        _completed_session(
            user_id=user_id,
            weekday=1,
            completed_at=activated - timedelta(days=1),
        ),
        _completed_session(
            user_id=user_id,
            weekday=3,
            completed_at=activated + timedelta(days=2),
        ),
    ]
    progress = training_week_progress(program, sessions, timezone_offset="+03:00")
    assert progress.completed_weekdays == [3]
    assert progress.week_finished is False


def test_week_progress_timezone_edge_shifts_local_weekday() -> None:
    # 2026-09-14 22:00 UTC → +03:00 is Tue 01:00 (weekday 2); -05:00 is Mon 17:00 (weekday 1)
    activated = datetime(2026, 9, 14, 22, 0, tzinfo=UTC)
    program = _program(weekdays=[1, 2], activated_at=activated)
    user_id = program.user_id
    # Ad-hoc session without a program weekday: fall back to the local completion date.
    session = _completed_session(user_id=user_id, weekday=None, completed_at=activated)

    plus_three = training_week_progress(program, [session], timezone_offset="+03:00")
    assert plus_three.week_started_on.isoformat() == "2026-09-15"
    assert plus_three.completed_weekdays == [2]

    minus_five = training_week_progress(program, [session], timezone_offset="-05:00")
    assert minus_five.week_started_on.isoformat() == "2026-09-14"
    assert minus_five.completed_weekdays == [1]


def test_week_progress_without_activation_is_not_finished() -> None:
    program = Program(
        user_id=uuid4(),
        program_type=ProgramType.FULL_BODY,
        status=ProgramStatus.ACTIVE,
        days=[WorkoutDay(weekday=1, title="День 1", position=1, slots=[_slot()])],
        activated_at=None,
    )
    progress = training_week_progress(program, [], timezone_offset="+03:00")
    assert progress.week_started_on is None
    assert progress.week_finished is False
    assert progress.planned_weekdays == [1]


def test_week_progress_counts_program_day_done_on_another_calendar_day() -> None:
    activated = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)  # Monday
    program = _program(weekdays=[1, 3, 5], activated_at=activated)
    # Wednesday's workout done on Thursday (a rest day).
    session = _completed_session(user_id=program.user_id, weekday=3, completed_at=activated + timedelta(days=3))
    progress = training_week_progress(program, [session], timezone_offset="+03:00")
    assert progress.completed_weekdays == [3]


def test_nearest_open_training_day_goes_forward_cyclically() -> None:
    program = _program(weekdays=[1, 3, 5], activated_at=datetime(2026, 9, 14, tzinfo=UTC))
    day = nearest_open_training_day(program, [1], today_weekday=4)
    assert day is not None and day.weekday == 5
    day = nearest_open_training_day(program, [1, 5], today_weekday=6)
    assert day is not None and day.weekday == 3
    day = nearest_open_training_day(program, [], today_weekday=3, exclude_weekdays=[3])
    assert day is not None and day.weekday == 5
    assert nearest_open_training_day(program, [1, 3, 5], today_weekday=2) is None
