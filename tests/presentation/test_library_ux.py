from __future__ import annotations

from uuid import uuid4

from fitness_bot.domain.enums import ExpectedInput
from fitness_bot.presentation.keyboards import (
    library_card_keyboard,
    library_day_keyboard,
    library_delete_confirm_keyboard,
    library_edit_proposal_keyboard,
    library_slot_keyboard,
    library_title_keyboard,
)
from fitness_bot.presentation.routers.library import (
    LIBRARY_EDIT_FIELD_PREFIX,
    LIBRARY_TITLE_FIELD_PREFIX,
    library_field_program_id,
)
from fitness_bot.presentation.routers.text import voice_input_allowed
from fitness_bot.presentation.templates_env import create_jinja_env


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_card_keyboard_has_days_edit_rename_delete_and_fits_callback_limit() -> None:
    program_id = str(uuid4())
    markup = library_card_keyboard(
        program_id=program_id,
        status="draft",
        is_author_template=True,
        days=[(1, "день 1 · пн"), (2, "день 2 · ср")],
    )
    callbacks = _callbacks(markup)
    assert f"lib_day:{program_id}:1" in callbacks
    assert f"lib_edit:{program_id}" in callbacks
    assert f"lib_rename:{program_id}" in callbacks
    assert f"lib_del:{program_id}" in callbacks
    assert f"lib_pub:{program_id}" in callbacks
    assert f"lib_apply:{program_id}:as_is" in callbacks

    nested = [
        *_callbacks(library_day_keyboard(program_id=program_id, day_position=7, slots=[(12, "Жим")])),
        *_callbacks(
            library_slot_keyboard(program_id=program_id, day_position=7, slot_position=12, has_catalog_guide=True)
        ),
        *_callbacks(library_edit_proposal_keyboard(program_id=program_id, can_approve=True)),
        *_callbacks(library_delete_confirm_keyboard(program_id=program_id)),
        *_callbacks(library_title_keyboard(program_id=program_id, has_draft=True)),
    ]
    assert all(len(data.encode()) <= 64 for data in [*callbacks, *nested])


def test_published_card_offers_unpublish_not_publish() -> None:
    program_id = str(uuid4())
    callbacks = _callbacks(
        library_card_keyboard(program_id=program_id, status="published", is_author_template=True, share_url=None),
    )
    assert f"lib_unpub:{program_id}" in callbacks
    assert f"lib_pub:{program_id}" not in callbacks
    assert f"lib_edit:{program_id}" in callbacks


def test_library_field_parsing_and_voice_for_title() -> None:
    program_id = uuid4()
    assert (
        library_field_program_id(f"{LIBRARY_TITLE_FIELD_PREFIX}{program_id}", LIBRARY_TITLE_FIELD_PREFIX) == program_id
    )
    assert library_field_program_id(f"{LIBRARY_EDIT_FIELD_PREFIX}{program_id}", LIBRARY_TITLE_FIELD_PREFIX) is None
    assert library_field_program_id(f"{LIBRARY_TITLE_FIELD_PREFIX}oops", LIBRARY_TITLE_FIELD_PREFIX) is None
    assert voice_input_allowed(
        expected_input=ExpectedInput.PROFILE_FIELD,
        expected_field=f"{LIBRARY_TITLE_FIELD_PREFIX}{program_id}",
    )


def _card_context(*, compact: bool) -> dict:
    slot = {
        "position": 1,
        "exercise_name": "Жим лёжа",
        "exercise_id": "x",
        "custom_request": None,
        "sets": 4,
        "reps": 8,
        "duration_seconds": None,
        "weight_kg": 60,
        "rest_seconds": 90,
        "rpe": 8,
    }
    return {
        "compact": compact,
        "title": "Моя <сила>",
        "status_icon": "📗",
        "status_label": "черновик",
        "program_type_label": "Фулбоди",
        "author_label": None,
        "code": None,
        "link": None,
        "claim_note": "",
        "status_line": None,
        "document": {"days": [{"weekday_label": "пн", "title": "Грудь", "slots": [slot]}]},
    }


def test_card_template_shows_exercises_with_sets_and_reps() -> None:
    template = create_jinja_env().get_template("library_card.j2")
    full = template.render(**_card_context(compact=False))
    assert "Моя &lt;сила&gt;" in full
    assert "пн — Грудь" in full
    assert "Жим лёжа" in full and "4×8" in full and "60 кг" in full

    compact = template.render(**_card_context(compact=True))
    assert "Жим лёжа" not in compact
    assert "1 упражнение" in compact
