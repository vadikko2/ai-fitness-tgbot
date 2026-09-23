from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from fitness_bot.domain.enums import ProgramType, WorkoutIntensity
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay, WorkoutDocument
from fitness_bot.domain.workout.session import Session
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.presentation.keyboards import slot_actions_keyboard
from fitness_bot.presentation.routers.session import (
    _next_open_slot_position,
    _parse_weight_kg,
)
from fitness_bot.service.handlers.commands.session import RecordSlotActualCommandHandler
from fitness_bot.service.handlers.commands.users import EnsureUserCommandHandler
from fitness_bot.service.models.commands.session import RecordSlotActualCommand
from fitness_bot.service.models.commands.users import EnsureUserCommand


@pytest.mark.asyncio
async def test_record_slot_actual_saves_weight_and_reps() -> None:
    uow = InMemoryUow()
    await EnsureUserCommandHandler(uow).handle(
        EnsureUserCommand(telegram_user_id=42, chat_id=42),
    )
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(42)
        assert user is not None
        session = Session.from_document(
            user_id=user.id,
            document=WorkoutDocument(
                program_type=ProgramType.FULL_BODY,
                days=[
                    WorkoutDay(
                        weekday=1,
                        title="День 1",
                        position=1,
                        intensity=WorkoutIntensity.MEDIUM,
                        slots=[
                            ExerciseSlot(
                                position=1,
                                exercise_id=uuid4(),
                                sets=4,
                                reps=8,
                                weight_kg=Decimal("80"),
                                rest_seconds=90,
                                rpe=7,
                            ),
                            ExerciseSlot(
                                position=2,
                                exercise_id=uuid4(),
                                sets=3,
                                reps=10,
                                rest_seconds=60,
                                rpe=6,
                            ),
                        ],
                    ),
                ],
            ),
        )
        saved = await repos.sessions.add(session)
        user.active_session_id = saved.id
        await repos.users.save(user)

    result = await RecordSlotActualCommandHandler(uow).handle(
        RecordSlotActualCommand(
            telegram_user_id=42,
            slot_position=1,
            sets=4,
            reps=6,
            weight_kg=Decimal("82.5"),
        ),
    )
    slot = result.document.days[0].slots[0]
    assert slot.actual is not None
    assert slot.actual.reps == 6
    assert slot.actual.weight_kg == Decimal("82.5")
    assert slot.actual.sets == 4
    assert result.document.days[0].slots[1].actual is None


def test_next_open_slot_skips_completed() -> None:
    document = WorkoutDocument(
        program_type=ProgramType.SPLIT,
        days=[
            WorkoutDay(
                weekday=2,
                title="День",
                position=1,
                intensity=WorkoutIntensity.LIGHT,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=uuid4(),
                        sets=3,
                        reps=8,
                        rest_seconds=60,
                        rpe=7,
                        actual=SlotActual(sets=3, reps=8),
                    ),
                    ExerciseSlot(
                        position=2,
                        exercise_id=uuid4(),
                        sets=3,
                        reps=10,
                        rest_seconds=60,
                        rpe=6,
                    ),
                ],
            ),
        ],
    )
    assert _next_open_slot_position(document, 1) == 2
    document.days[0].slots[1] = document.days[0].slots[1].with_actual(SlotActual(sets=3, reps=10))
    assert _next_open_slot_position(document, 2) is None


def test_parse_weight_accepts_comma_and_bodyweight() -> None:
    assert _parse_weight_kg("82,5") == Decimal("82.5")
    assert _parse_weight_kg("без") is None
    assert _parse_weight_kg("0") is None


def test_slot_actions_keyboard_labels() -> None:
    markup = slot_actions_keyboard(position=3, has_catalog_guide=True)
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert "✅ Как в плане → дальше" in labels
    assert "✏️ Вес и повторы" in labels
    assert "📖 Как делать" in labels
