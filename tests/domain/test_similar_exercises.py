from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from fitness_bot.domain.catalog.similar import similar_exercises, similarity_score
from fitness_bot.domain.enums import ProgramStatus, ProgramType, TrainingPlace
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay
from fitness_bot.domain.workout.program import Program
from fitness_bot.domain.workout.session import Session
from fitness_bot.service.ports.exercise_catalog import record

BENCH = record(
    exercise_id=uuid4(),
    name="Жим штанги лёжа",
    primary_muscles=["грудь"],
    secondary_muscles=["трицепс", "плечи"],
)
DB_BENCH = record(
    exercise_id=uuid4(),
    name="Жим гантелей лёжа",
    primary_muscles=["грудь"],
    secondary_muscles=["трицепс", "плечи"],
    places=["gym", "home"],
)
MACHINE = record(
    exercise_id=uuid4(),
    name="Жим в тренажёре сидя",
    primary_muscles=["грудь"],
    secondary_muscles=["трицепс"],
)
PUSHUP = record(
    exercise_id=uuid4(),
    name="Отжимания от пола",
    primary_muscles=["грудь"],
    secondary_muscles=["трицепс", "плечи", "пресс"],
    places=["gym", "home", "outdoor"],
)
STRETCH = record(
    exercise_id=uuid4(),
    name="Растяжка: грудь у стены",
    primary_muscles=["грудь"],
    places=["gym", "home"],
)
BURPEE = record(
    exercise_id=uuid4(),
    name="Бёрпи",
    primary_muscles=["грудь", "квадрицепс", "ягодицы", "пресс"],
    places=["gym", "home"],
)
SQUAT = record(exercise_id=uuid4(), name="Приседания со штангой", primary_muscles=["квадрицепс"])
POOL = [BENCH, DB_BENCH, MACHINE, PUSHUP, STRETCH, BURPEE, SQUAT]


def test_similar_ranks_same_muscles_and_movement_first() -> None:
    page = similar_exercises(BENCH, POOL, training_place=TrainingPlace.GYM, limit=3)
    names = [item.name for item in page.items]
    assert names[0] == "Жим гантелей лёжа"
    assert set(names) == {"Жим гантелей лёжа", "Жим в тренажёре сидя", "Отжимания от пола"}
    # Бёрпи hits the chest too, but its extra primary muscles cancel the overlap.
    assert BURPEE.id not in {item.exercise_id for item in page.items}
    assert page.has_more is False


def test_similar_excludes_other_muscles_categories_and_todays_exercises() -> None:
    page = similar_exercises(BENCH, POOL, training_place=TrainingPlace.GYM, exclude_ids={DB_BENCH.id}, limit=10)
    ids = {item.exercise_id for item in page.items}
    assert BENCH.id not in ids and DB_BENCH.id not in ids
    assert SQUAT.id not in ids
    assert STRETCH.id not in ids
    assert similarity_score(BENCH, SQUAT) == 0


def test_similar_respects_training_place_and_pagination() -> None:
    home = similar_exercises(BENCH, POOL, training_place=TrainingPlace.HOME, limit=10)
    assert MACHINE.id not in {item.exercise_id for item in home.items}
    first = similar_exercises(BENCH, POOL, training_place=TrainingPlace.GYM, limit=2)
    second = similar_exercises(BENCH, POOL, training_place=TrainingPlace.GYM, offset=2, limit=2)
    assert not {item.exercise_id for item in first.items} & {item.exercise_id for item in second.items}
    assert second.has_more is False


def _slot(position: int = 1) -> ExerciseSlot:
    return ExerciseSlot(
        position=position,
        exercise_id=BENCH.id,
        sets=4,
        reps=8,
        weight_kg=Decimal("60"),
        rest_seconds=120,
        rpe=8,
        technique_note="лопатки сведены",
    )


def _session() -> Session:
    return Session.from_template_day(
        user_id=uuid4(),
        program_type=ProgramType.FULL_BODY,
        day=WorkoutDay(weekday=1, title="Грудь", position=1, slots=[_slot()]),
    )


def test_session_swap_keeps_plan_and_sets_weight() -> None:
    session = _session()
    swapped = session.swap_slot_exercise(1, DB_BENCH.id, weight_kg=None)
    assert swapped.exercise_id == DB_BENCH.id
    assert (swapped.sets, swapped.reps, swapped.rest_seconds, swapped.rpe) == (4, 8, 120, 8)
    assert swapped.weight_kg is None
    assert swapped.technique_note == ""
    assert session.slot_at(1).id == swapped.id


def test_session_swap_is_blocked_after_logged_sets_or_completion() -> None:
    session = _session()
    session.apply_slot_actual(1, SlotActual(sets=4, reps=8, weight_kg=Decimal("60")))
    with pytest.raises(DomainError):
        session.swap_slot_exercise(1, DB_BENCH.id, weight_kg=None)
    finished = _session()
    finished.finalize()
    with pytest.raises(DomainError):
        finished.swap_slot_exercise(1, DB_BENCH.id, weight_kg=None)


def test_program_replace_slot_exercise_only_for_active_program() -> None:
    day = WorkoutDay(weekday=1, title="Грудь", position=1, slots=[_slot()])
    program = Program(user_id=uuid4(), program_type=ProgramType.FULL_BODY, days=[day])
    assert program.template_day_for(day) is not None
    program.replace_slot_exercise(day_position=1, slot_position=1, exercise_id=PUSHUP.id, weight_kg=None)
    assert program.days[0].slots[0].exercise_id == PUSHUP.id
    assert program.days[0].slots[0].sets == 4
    program.status = ProgramStatus.DRAFT
    with pytest.raises(DomainError):
        program.replace_slot_exercise(day_position=1, slot_position=1, exercise_id=BENCH.id, weight_kg=None)
