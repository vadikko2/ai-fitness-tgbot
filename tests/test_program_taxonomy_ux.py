from __future__ import annotations

from fitness_bot.domain.enums import ProgramType
from fitness_bot.domain.program_catalog import PROGRAM_TYPE_COPY, structure_choice_items
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
