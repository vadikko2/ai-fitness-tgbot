from __future__ import annotations

from uuid import uuid4

import pytest

from fitness_bot.domain.enums import ProgramType, SessionStatus, TrainingStyle, WorkoutIntensity
from fitness_bot.domain.errors import DomainError, EmptyProgramWeek, InvalidWorkoutDocument, UnresolvedExercises
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay, WorkoutDocument
from fitness_bot.domain.workout.session import Session
from fitness_bot.domain.workout.technique_video import TechniqueVideo, technique_video_object_key


def test_workout_day_defaults_intensity_to_medium() -> None:
    day = WorkoutDay(title="День 1", position=1, slots=[])
    assert day.intensity == WorkoutIntensity.MEDIUM


def test_workout_day_defaults_training_style_to_classic() -> None:
    day = WorkoutDay(title="День 1", position=1, slots=[])
    assert day.training_style == TrainingStyle.CLASSIC


def test_workout_day_defaults_warmup_cooldown_empty() -> None:
    day = WorkoutDay(title="День 1", position=1, slots=[])
    assert day.warmup == ""
    assert day.cooldown == ""


def test_reps_xor_duration() -> None:
    with pytest.raises(InvalidWorkoutDocument):
        ExerciseSlot(position=1, exercise_id=uuid4(), sets=3, rest_seconds=60, rpe=5)


def test_unresolved_requires_custom_fields() -> None:
    with pytest.raises(InvalidWorkoutDocument):
        ExerciseSlot(position=1, sets=3, reps=8, rest_seconds=60, rpe=5)


def test_approve_requires_resolved_slots() -> None:
    doc = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                title="День 1",
                position=1,
                slots=[
                    ExerciseSlot(
                        position=1,
                        custom_request="жим",
                        muscle_group="грудь",
                        sets=3,
                        reps=8,
                        rest_seconds=60,
                        rpe=7,
                    ),
                ],
            ),
        ],
    )
    with pytest.raises(UnresolvedExercises):
        doc.assert_approvable()


def test_approve_empty_week() -> None:
    with pytest.raises(EmptyProgramWeek):
        WorkoutDocument(program_type=ProgramType.SPLIT, days=[]).assert_approvable()


def _resolved_slot() -> ExerciseSlot:
    return ExerciseSlot(
        position=1,
        exercise_id=uuid4(),
        sets=3,
        reps=8,
        rest_seconds=60,
        rpe=7,
    )


def test_replace_day_keeps_other_days() -> None:
    day1 = WorkoutDay(weekday=1, title="День 1", position=1, slots=[_resolved_slot()])
    day2 = WorkoutDay(weekday=3, title="День 2", position=2, slots=[_resolved_slot()])
    doc = WorkoutDocument(program_type=ProgramType.FULL_BODY, days=[day1, day2])
    updated = day1.model_copy(
        update={
            "warmup": "суставная разминка",
            "slots": [day1.slots[0].model_copy(update={"sets": 5})],
        },
    )
    result = doc.replace_day(updated)
    assert result.days[0].slots[0].sets == 5
    assert result.days[0].warmup == "суставная разминка"
    assert result.days[1].title == "День 2"
    assert result.days[1].slots[0].sets == day2.slots[0].sets


def test_assert_schedule_complete_requires_weekday() -> None:
    doc = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[WorkoutDay(title="День 1", position=1, slots=[_resolved_slot()])],
    )
    with pytest.raises(InvalidWorkoutDocument, match="weekday"):
        doc.assert_schedule_complete()


def test_assert_schedule_complete_rejects_duplicate_weekdays() -> None:
    doc = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(weekday=2, title="День 1", position=1, slots=[_resolved_slot()]),
            WorkoutDay(weekday=2, title="День 2", position=2, slots=[_resolved_slot()]),
        ],
    )
    with pytest.raises(InvalidWorkoutDocument, match="unique"):
        doc.assert_schedule_complete()


def test_assert_approvable_with_schedule_blocks_missing_weekday() -> None:
    doc = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(title="День 1", position=1, slots=[_resolved_slot()]),
        ],
    )
    with pytest.raises(InvalidWorkoutDocument, match="weekday"):
        doc.assert_approvable(require_schedule=True)


def test_assert_approvable_without_schedule_allows_missing_weekday() -> None:
    doc = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(title="День 1", position=1, slots=[_resolved_slot()]),
        ],
    )
    doc.assert_approvable()


def test_assert_schedule_complete_matches_days_per_week() -> None:
    doc = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(weekday=2, title="День 1", position=1, slots=[_resolved_slot()]),
            WorkoutDay(weekday=4, title="День 2", position=2, slots=[_resolved_slot()]),
        ],
    )
    with pytest.raises(InvalidWorkoutDocument, match="days_per_week"):
        doc.assert_schedule_complete(days_per_week=3)
    doc.assert_schedule_complete(days_per_week=2)


def test_session_confirm_and_complete() -> None:
    exercise_id = uuid4()
    template_slot_id = uuid4()
    day = WorkoutDay(
        title="День",
        position=1,
        weekday=1,
        slots=[
            ExerciseSlot(
                id=template_slot_id,
                position=1,
                exercise_id=exercise_id,
                sets=3,
                reps=8,
                rest_seconds=60,
                rpe=7,
                weight_kg=40,
            ),
        ],
    )
    session = Session.from_template_day(
        user_id=uuid4(),
        program_type=ProgramType.FULL_BODY,
        day=day,
    )
    assert session.day.slots[0].id is not None
    assert session.day.slots[0].id != template_slot_id
    assert session.day.slots[0].actual is None
    slot = session.confirm_slot_as_planned(1)
    assert slot.actual == SlotActual(sets=3, reps=8, weight_kg=40, note="")
    session.begin_completion()
    assert session.status == SessionStatus.PENDING_COMPLETION
    assert session.day.slots[0].actual is not None
    session.clear_actuals()
    assert session.status == SessionStatus.IN_PROGRESS
    assert all(slot.actual is None for slot in session.day.slots)
    session.begin_completion()
    assert session.status == SessionStatus.PENDING_COMPLETION
    assert session.day.slots[0].actual is not None
    session.finalize()
    assert session.status == SessionStatus.COMPLETED
    assert session.completed_at is not None


def test_technique_video_key_and_replace_clears_file_id() -> None:
    user_id = uuid4()
    session_id = uuid4()
    slot_id = uuid4()
    video = TechniqueVideo.create(
        slot_id=slot_id,
        user_id=user_id,
        session_id=session_id,
        content_type="video/mp4",
        byte_size=12,
    )
    assert video.object_key == technique_video_object_key(
        user_id=user_id,
        session_id=session_id,
        slot_id=slot_id,
    )
    remembered = video.remember_telegram_file_id("tg-1")
    assert remembered.telegram_file_id == "tg-1"
    replaced = remembered.replace_file(content_type="video/webm", byte_size=20)
    assert replaced.telegram_file_id is None
    assert replaced.content_type == "video/webm"
    with pytest.raises(DomainError):
        TechniqueVideo.create(
            slot_id=slot_id,
            user_id=user_id,
            session_id=session_id,
            content_type="image/png",
            byte_size=12,
        )


def test_update_slot_planned_weight_and_reps() -> None:
    from decimal import Decimal

    exercise_id = uuid4()
    doc = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                title="День 1",
                position=1,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=exercise_id,
                        sets=3,
                        reps=8,
                        weight_kg=Decimal("60"),
                        rest_seconds=60,
                        rpe=7,
                    ),
                ],
            ),
        ],
    )
    updated = doc.update_slot_planned(
        day_position=1,
        slot_position=1,
        weight_kg=Decimal("70"),
        reps=10,
    )
    slot = updated.days[0].slots[0]
    assert slot.weight_kg == Decimal("70")
    assert slot.reps == 10
    assert slot.sets == 3
