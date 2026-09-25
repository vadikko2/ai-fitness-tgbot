from __future__ import annotations

from fitness_bot.domain.enums import ProgramType
from fitness_bot.domain.program_catalog import PROGRAM_TYPE_COPY, program_status_label, structure_choice_items
from fitness_bot.domain.workout.program import Program
from fitness_bot.presentation.keyboards import program_type_keyboard
from fitness_bot.presentation.templates_env import create_jinja_env


def test_structure_menu_lists_all_program_types() -> None:
    text = (
        create_jinja_env()
        .get_template("program_structure_menu.j2")
        .render(
            structure_items=structure_choice_items(),
        )
    )
    for program_type in ProgramType:
        copy = PROGRAM_TYPE_COPY[program_type]
        assert copy.blurb in text
        assert f"<b>{copy.label}</b>" in text
    assert "&lt;b&gt;" not in text


def test_program_type_keyboard_callback_prefixes() -> None:
    markup = program_type_keyboard()
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "prog_type:full_body" in callbacks
    assert "prog_type:upper_lower" in callbacks
    assert "prog_type:antagonist" in callbacks
    assert "prog_type:kettlebell" in callbacks
    assert "prog_type:cardio" in callbacks
    assert "prog_type:bodyweight_recovery" in callbacks
    assert "prog_type:stretching" in callbacks


def test_exercise_place_filter_excludes_gym_only_for_home() -> None:
    from fitness_bot.domain.catalog.places import exercise_matches_training_place
    from fitness_bot.domain.enums import TrainingPlace

    assert exercise_matches_training_place(["home", "outdoor"], TrainingPlace.HOME)
    assert not exercise_matches_training_place(["gym"], TrainingPlace.HOME)
    assert exercise_matches_training_place(["gym"], TrainingPlace.GYM)
    assert exercise_matches_training_place(["gym", "home"], TrainingPlace.MIXED)


def test_program_display_title_and_status_are_russian() -> None:
    from uuid import uuid4

    from fitness_bot.domain.enums import ProgramStatus

    program = Program(
        user_id=uuid4(),
        program_type=ProgramType.FULL_BODY,
        status=ProgramStatus.ACTIVE,
        title=None,
    )
    assert program.display_title() == PROGRAM_TYPE_COPY[ProgramType.FULL_BODY].label

    legacy = Program(
        user_id=uuid4(),
        program_type=ProgramType.FULL_BODY,
        status=ProgramStatus.ACTIVE,
        title="Full Body",
    )
    assert legacy.display_title() == PROGRAM_TYPE_COPY[ProgramType.FULL_BODY].label

    custom = Program(
        user_id=uuid4(),
        program_type=ProgramType.FULL_BODY,
        status=ProgramStatus.ACTIVE,
        title="Мой план",
    )
    assert custom.display_title() == "Мой план"

    assert program_status_label("draft") == "черновик"
    assert program_status_label(ProgramStatus.PUBLISHED) == "опубликована"
