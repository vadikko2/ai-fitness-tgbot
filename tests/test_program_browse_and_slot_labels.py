from __future__ import annotations

from uuid import uuid4

from fitness_bot.domain.enums import ProgramType, WorkoutIntensity
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay, WorkoutDocument
from fitness_bot.presentation.keyboards import (
    program_day_keyboard,
    program_slot_keyboard,
    session_card_keyboard,
)
from fitness_bot.presentation.routers.program import _slot_button_items
from fitness_bot.presentation.routers.session import _slot_button_items as session_slot_button_items
from fitness_bot.presentation.templates_env import create_jinja_env


def test_session_card_keyboard_shows_exercise_names() -> None:
    markup = session_card_keyboard(slots=[(1, "Приседания"), (2, "Жим лёжа")])
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert labels[0] == "1. Приседания"
    assert labels[1] == "2. Жим лёжа"
    assert "🔄 Начать заново" in labels
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "sess_restart" in callbacks


def test_session_slot_button_items_omit_slots_with_actual() -> None:
    exercise_id = uuid4()
    day = WorkoutDay(
        weekday=1,
        title="День 1",
        position=1,
        intensity=WorkoutIntensity.MEDIUM,
        slots=[
            ExerciseSlot(
                position=1,
                exercise_id=exercise_id,
                sets=3,
                reps=8,
                rest_seconds=60,
                rpe=7,
                actual=SlotActual(sets=3, reps=8),
            ),
            ExerciseSlot(
                position=2,
                custom_request="Планка",
                muscle_group="кор",
                sets=3,
                duration_seconds=45,
                rest_seconds=45,
                rpe=6,
            ),
        ],
    )
    document = WorkoutDocument(program_type=ProgramType.SPLIT, days=[day])
    items = session_slot_button_items(document, {exercise_id: "Приседания"})
    assert items == [(2, "Планка")]
    markup = session_card_keyboard(slots=items)
    texts = [button.text for row in markup.inline_keyboard for button in row]
    assert texts[0] == "2. Планка"
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "slot:1" not in callbacks
    assert "slot:2" in callbacks


def test_program_day_keyboard_opens_named_slots() -> None:
    markup = program_day_keyboard(day_position=2, slots=[(1, "Тяга"), (3, "Планка")])
    assert markup.inline_keyboard[0][0].text == "1. Тяга"
    assert markup.inline_keyboard[0][0].callback_data == "prog_view_slot:2:1"
    assert markup.inline_keyboard[1][0].callback_data == "prog_view_slot:2:3"
    assert markup.inline_keyboard[1][0].text == "3. Планка"


def test_program_slot_keyboard_shows_guide_when_available() -> None:
    with_guide = program_slot_keyboard(day_position=1, slot_position=2, has_catalog_guide=True)
    assert with_guide.inline_keyboard[0][0].callback_data == "prog_view_how:1:2"
    without = program_slot_keyboard(day_position=1, slot_position=2, has_catalog_guide=False)
    assert without.inline_keyboard[0][0].callback_data == "prog_view_day:1"


def test_slot_button_items_prefer_catalog_name() -> None:
    exercise_id = uuid4()
    day = WorkoutDay(
        weekday=2,
        title="День 1",
        position=1,
        intensity=WorkoutIntensity.MEDIUM,
        slots=[
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
        ],
    )
    items = _slot_button_items(day, {exercise_id: "Выпады"})
    assert items == [(1, "Выпады"), (2, "своё")]

    document = WorkoutDocument(program_type=ProgramType.SPLIT, days=[day])
    assert session_slot_button_items(document, {exercise_id: "Выпады"}) == items


def test_program_slot_template_renders_plan_only() -> None:
    text = (
        create_jinja_env()
        .get_template("program_slot.j2")
        .render(
            slot={
                "position": 1,
                "exercise_name": "Жим",
                "custom_request": None,
                "sets": 4,
                "reps": 8,
                "duration_seconds": None,
                "weight_kg": 60,
                "rest_seconds": 90,
                "rpe": 7,
            },
        )
    )
    assert "1. Жим" in text
    assert "4×8" in text
    assert "Факт" not in text


def test_exercise_guide_keyboard_has_no_how_button() -> None:
    from fitness_bot.presentation.keyboards import exercise_guide_keyboard

    markup = exercise_guide_keyboard(
        videos=[("rutube", "https://rutube.ru/video/abc/", "Румынская тяга")],
        back_callback="prog_view_slot:1:5",
    )
    labels = [button.text or "" for row in markup.inline_keyboard for button in row]
    assert all("Как делать" not in label for label in labels)
    assert any(label.startswith("🎥") for label in labels)
