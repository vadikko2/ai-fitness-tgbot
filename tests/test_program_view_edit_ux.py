from __future__ import annotations

from fitness_bot.domain.enums import ProposalKind
from fitness_bot.presentation.keyboards import (
    program_edit_menu_keyboard,
    program_screen_keyboard,
    proposal_actions_keyboard,
)
from fitness_bot.presentation.routers.program import _is_program_draft
from fitness_bot.presentation.templates_env import create_jinja_env


def test_program_after_type_keyboard_has_text_or_voice() -> None:
    from fitness_bot.presentation.keyboards import program_after_type_keyboard

    markup = program_after_type_keyboard()
    labels = [button.text for row in markup.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "✏️ Описать текстом или голосом" in labels
    assert "prog_text" in callbacks
    assert "✨ Пусть предложит" in labels


def test_proposal_after_type_template_mentions_buttons() -> None:
    text = (
        create_jinja_env()
        .get_template("proposal.j2")
        .render(
            reply="",
            document=None,
            program_type_label="🧍 Фуллбади",
            program_type_blurb="Каждую тренировку — всё тело.",
            missing_weekdays=False,
        )
    )
    assert "📋 Программа" in text
    assert "Описать текстом или голосом" in text
    assert "Пусть предложит" in text
    assert "Черновик программы" not in text

    markup = program_screen_keyboard(has_pending=True, has_active=True, days=[(1, "день 1 · Вт")])
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert labels[0] == "📅 день 1 · Вт"
    assert "✏️ Изменить программу" in labels
    assert "📝 Есть черновик — открыть" in labels
    assert "Подтвердить" not in " ".join(labels)
    assert "Отмена" not in " ".join(labels)


def test_program_edit_menu_keyboard() -> None:
    markup = program_edit_menu_keyboard(has_pending=True)
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert "📝 Открыть черновик" in labels
    assert "🔄 Задать / сменить программу" in labels


def test_proposal_actions_use_draft_labels() -> None:
    markup = proposal_actions_keyboard(can_approve=True, days=[(1, "день 1")])
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert "✅ Сделать активной" in labels
    assert "❌ Отменить черновик" in labels
    assert "✏️ Изменить текстом или голосом" in labels


def test_is_program_draft_ignores_other_kinds() -> None:
    class Pending:
        proposal_id = "x"
        has_document = True
        document = object()
        kind = ProposalKind.WORKOUT_EDIT

    assert _is_program_draft(Pending()) is False
    Pending.kind = ProposalKind.PROGRAM
    assert _is_program_draft(Pending()) is True


def test_proposal_template_explains_draft_actions() -> None:
    text = (
        create_jinja_env()
        .get_template("proposal.j2")
        .render(
            reply="",
            document={
                "days": [
                    {
                        "weekday_label": "Вт",
                        "title": "день 1",
                        "intensity_label": "средняя",
                        "training_style_label": "🏋️ Классика",
                        "slots": [1, 2],
                    },
                ],
            },
            program_type_label="🧩 Бро-сплит",
            program_type_blurb="Одна группа в день.",
            missing_weekdays=False,
        )
    )
    assert "Черновик программы" in text
    assert "Сделать активной" in text
    assert "Отменить черновик" in text
    assert "1 тренировка" in text
    assert "Вт — день 1" in text
    assert "Средняя тренировка, 2 упражнения." in text
    assert " · средняя · " not in text


def test_proposal_day_keyboard_lists_slots() -> None:
    from fitness_bot.presentation.keyboards import proposal_day_keyboard, proposal_slot_keyboard

    markup = proposal_day_keyboard(
        day_position=2,
        slots=[(1, "Жим"), (2, "Тяга")],
    )
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert "pdraft_slot:2:1" in callbacks
    assert "pdraft_slot:2:2" in callbacks
    assert any((c or "").startswith("prog_edit_day:2") for c in callbacks)
    assert "prog_ok" not in callbacks
    assert "Сделать активной" not in " ".join(labels)

    slot_markup = proposal_slot_keyboard(day_position=2, slot_position=1, has_catalog_guide=True)
    slot_callbacks = [button.callback_data for row in slot_markup.inline_keyboard for button in row]
    slot_labels = [button.text for row in slot_markup.inline_keyboard for button in row]
    assert "pdraft_edit:2:1" in slot_callbacks
    assert "pdraft_how:2:1" in slot_callbacks
    assert "prog_day:2" in slot_callbacks
    assert "prog_ok" not in slot_callbacks
    assert any("К тренировке" in (label or "") for label in slot_labels)
