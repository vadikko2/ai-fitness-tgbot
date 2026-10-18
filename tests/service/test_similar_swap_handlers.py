from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from fitness_bot.domain.enums import ProgramStatus, ProgramType
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import local_calendar_date
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay
from fitness_bot.domain.workout.program import Program
from fitness_bot.domain.workout.session import Session
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.handlers.commands.session import (
    ConfirmExerciseAsPlannedCommandHandler,
    ReplaceProgramSlotFromSessionCommandHandler,
    StartTodayWorkoutCommandHandler,
    SwapSessionSlotExerciseCommandHandler,
)
from fitness_bot.service.handlers.commands.users import EnsureUserCommandHandler
from fitness_bot.service.handlers.queries.session import GetSimilarExercisesQueryHandler
from fitness_bot.service.models.commands.session import (
    ConfirmExerciseAsPlannedCommand,
    ReplaceProgramSlotFromSessionCommand,
    StartTodayWorkoutCommand,
    SwapSessionSlotExerciseCommand,
)
from fitness_bot.service.models.commands.users import EnsureUserCommand
from fitness_bot.service.models.queries.session import GetSimilarExercisesQuery
from fitness_bot.service.ports.exercise_catalog import InMemoryExerciseCatalog, record

TG = 31
BENCH = uuid4()
DB_BENCH = uuid4()
MACHINE = uuid4()
SQUAT = uuid4()
LEG_PRESS = uuid4()


def _catalog() -> InMemoryExerciseCatalog:
    return InMemoryExerciseCatalog(
        exercises=[
            record(exercise_id=BENCH, name="Жим штанги лёжа", primary_muscles=["грудь"], secondary_muscles=["трицепс"]),
            record(
                exercise_id=DB_BENCH,
                name="Жим гантелей лёжа",
                primary_muscles=["грудь"],
                secondary_muscles=["трицепс"],
            ),
            record(exercise_id=MACHINE, name="Жим в тренажёре сидя", primary_muscles=["грудь"]),
            record(exercise_id=SQUAT, name="Приседания со штангой", primary_muscles=["квадрицепс"]),
            record(exercise_id=LEG_PRESS, name="Жим ногами", primary_muscles=["квадрицепс"]),
        ],
    )


def _slot(position: int, exercise_id, weight: str | None) -> ExerciseSlot:
    return ExerciseSlot(
        position=position,
        exercise_id=exercise_id,
        sets=4,
        reps=8,
        weight_kg=Decimal(weight) if weight else None,
        rest_seconds=120,
        rpe=8,
    )


async def _seed(uow: InMemoryUow) -> Program:
    await EnsureUserCommandHandler(uow).handle(EnsureUserCommand(telegram_user_id=TG, chat_id=310))
    today = local_calendar_date(now=datetime.now(UTC), timezone_offset=None).isoweekday()
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(TG)
        assert user is not None
        program = Program(
            user_id=user.id,
            program_type=ProgramType.FULL_BODY,
            status=ProgramStatus.ACTIVE,
            days=[
                WorkoutDay(
                    weekday=today,
                    title="Грудь и ноги",
                    position=1,
                    slots=[_slot(1, BENCH, "60"), _slot(2, SQUAT, "80")],
                ),
            ],
            activated_at=datetime.now(UTC) - timedelta(days=7),
        )
        await repos.programs.add(program)
        user.active_program_id = program.id
        past = Session.from_template_day(
            user_id=user.id,
            program_type=ProgramType.FULL_BODY,
            day=WorkoutDay(title="Старое", position=1, slots=[_slot(1, DB_BENCH, "20")]),
            now=datetime.now(UTC) - timedelta(days=3),
        )
        past.apply_slot_actual(1, SlotActual(sets=4, reps=8, weight_kg=Decimal("22.5")))
        past.finalize(now=datetime.now(UTC) - timedelta(days=3))
        await repos.sessions.add(past)
        await repos.users.save(user)
    await StartTodayWorkoutCommandHandler(uow).handle(StartTodayWorkoutCommand(telegram_user_id=TG))
    return program


async def _swap(uow: InMemoryUow, exercise_id, position: int = 1):
    return await SwapSessionSlotExerciseCommandHandler(uow, _catalog()).handle(
        SwapSessionSlotExerciseCommand(telegram_user_id=TG, slot_position=position, exercise_id=exercise_id),
    )


async def test_similar_excludes_exercises_already_in_todays_workout() -> None:
    uow = InMemoryUow()
    await _seed(uow)
    result = await GetSimilarExercisesQueryHandler(uow, _catalog()).handle(
        GetSimilarExercisesQuery(telegram_user_id=TG, slot_position=1),
    )
    assert result.blocked_reason is None
    assert result.exercise_name == "Жим штанги лёжа"
    ids = [item.exercise_id for item in result.items]
    assert ids[0] == DB_BENCH
    assert set(ids) == {DB_BENCH, MACHINE}
    assert result.has_more is False


async def test_swap_uses_history_weight_then_none_then_program_on_revert() -> None:
    uow = InMemoryUow()
    await _seed(uow)

    from_history = await _swap(uow, DB_BENCH)
    assert from_history.previous_exercise_id == BENCH
    assert from_history.slot.exercise_id == DB_BENCH
    assert from_history.weight_source == "history"
    assert from_history.slot.weight_kg == Decimal("22.5")
    assert (from_history.slot.sets, from_history.slot.reps) == (4, 8)
    assert from_history.can_replace_in_program is True

    unknown = await _swap(uow, MACHINE)
    assert unknown.weight_source == "none"
    assert unknown.slot.weight_kg is None

    reverted = await _swap(uow, BENCH)
    assert reverted.matches_program is True
    assert reverted.weight_source == "program"
    assert reverted.slot.weight_kg == Decimal("60")
    assert reverted.can_replace_in_program is False


async def test_replace_in_program_copies_swapped_exercise_into_active_day() -> None:
    uow = InMemoryUow()
    program = await _seed(uow)
    await _swap(uow, DB_BENCH)
    result = await ReplaceProgramSlotFromSessionCommandHandler(uow).handle(
        ReplaceProgramSlotFromSessionCommand(telegram_user_id=TG, slot_position=1),
    )
    assert result.day_title == "Грудь и ноги"
    async with uow.transaction() as repos:
        saved = await repos.programs.get_by_id(program.id)
        assert saved is not None
        slot = saved.days[0].slots[0]
        assert slot.exercise_id == DB_BENCH
        assert slot.weight_kg == Decimal("22.5")
        assert saved.days[0].slots[1].exercise_id == SQUAT


async def test_swap_is_blocked_after_sets_are_logged() -> None:
    uow = InMemoryUow()
    await _seed(uow)
    await ConfirmExerciseAsPlannedCommandHandler(uow).handle(
        ConfirmExerciseAsPlannedCommand(telegram_user_id=TG, slot_position=1),
    )
    result = await GetSimilarExercisesQueryHandler(uow, _catalog()).handle(
        GetSimilarExercisesQuery(telegram_user_id=TG, slot_position=1),
    )
    assert result.blocked_reason == "logged"
    assert result.items == []
    with pytest.raises(DomainError):
        await _swap(uow, DB_BENCH)


async def test_swap_rejects_unknown_exercise_and_requires_open_session() -> None:
    uow = InMemoryUow()
    await _seed(uow)
    with pytest.raises(DomainError):
        await _swap(uow, uuid4())
    other = InMemoryUow()
    await EnsureUserCommandHandler(other).handle(EnsureUserCommand(telegram_user_id=TG, chat_id=310))
    result = await GetSimilarExercisesQueryHandler(other, _catalog()).handle(
        GetSimilarExercisesQuery(telegram_user_id=TG, slot_position=1),
    )
    assert result.blocked_reason == "no_session"
