from __future__ import annotations

from uuid import uuid4

from fitness_bot.domain.workout.document import ExerciseSlot
from fitness_bot.presentation.keyboards import program_day_keyboard, session_card_keyboard
from fitness_bot.presentation.muscle_emoji import (
    build_slot_nav_items,
    slot_nav_button_text,
)


def test_slot_nav_button_text_and_keyboards() -> None:
    assert slot_nav_button_text(position=1, label="Приседания") == "1. Приседания"
    assert slot_nav_button_text(position=2, label="Жим") == "2. Жим"

    session = session_card_keyboard(
        slots=[
            (1, "Приседания"),
            (2, "Жим лёжа"),
            (7, "Планка"),
        ],
    )
    labels = [button.text for row in session.inline_keyboard for button in row]
    assert labels[0] == "1. Приседания"
    assert labels[1] == "2. Жим лёжа"
    assert labels[2] == "7. Планка"
    assert session.inline_keyboard[0][0].callback_data == "slot:1"

    program = program_day_keyboard(
        day_position=2,
        slots=[(1, "Тяга"), (3, "Планка")],
    )
    assert program.inline_keyboard[0][0].text == "1. Тяга"
    assert program.inline_keyboard[0][0].callback_data == "prog_view_slot:2:1"
    assert program.inline_keyboard[1][0].text == "3. Планка"


def test_build_slot_nav_items() -> None:
    exercise_id = uuid4()
    slots = [
        ExerciseSlot(
            position=1,
            exercise_id=exercise_id,
            sets=3,
            reps=8,
            rest_seconds=60,
            rpe=7,
        ),
        ExerciseSlot(
            position=2,
            custom_request="своё",
            muscle_group="ноги",
            sets=3,
            duration_seconds=40,
            rest_seconds=45,
            rpe=6,
        ),
    ]
    items = build_slot_nav_items(slots, names={exercise_id: "Выпады"})
    assert items == [(1, "Выпады"), (2, "своё")]
