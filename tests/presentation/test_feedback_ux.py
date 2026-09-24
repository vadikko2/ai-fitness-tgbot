from __future__ import annotations

from uuid import uuid4

from fitness_bot.domain.enums import ExpectedInput, FeedbackKind, FeedbackStatus
from fitness_bot.presentation.keyboards import (
    feedback_detail_keyboard,
    feedback_list_keyboard,
    feedback_list_label,
    feedback_moderator_keyboard,
    home_keyboard,
)
from fitness_bot.presentation.routers.feedback import author_status_text
from fitness_bot.presentation.routers.text import voice_input_allowed


def _callback_data(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _button_text(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_home_keyboard_has_idea_and_problem() -> None:
    callbacks = _callback_data(home_keyboard())
    assert "fb_menu:idea" in callbacks
    assert "fb_menu:problem" in callbacks


def test_my_ideas_page_shows_at_most_five_and_status_marks() -> None:
    items = [(uuid4(), FeedbackStatus.NEW, f"идея {index} " + ("длинный текст " * 4)) for index in range(6)]
    items[1] = (items[1][0], FeedbackStatus.IN_PROGRESS, items[1][2])
    items[2] = (items[2][0], FeedbackStatus.RESOLVED, items[2][2])
    items[3] = (items[3][0], FeedbackStatus.CANCELLED, items[3][2])
    markup = feedback_list_keyboard(kind=FeedbackKind.IDEA, items=items, offset=0, total=6)
    callbacks = _callback_data(markup)
    opens = [item for item in callbacks if item.startswith("fb_open:")]
    assert len(opens) == 5
    assert "fb_list:idea:5" in callbacks
    assert "fb_menu:idea" in callbacks
    assert "home" in callbacks
    labels = _button_text(markup)
    assert labels[0].startswith("⚪️")
    assert labels[1].startswith("🟡")
    assert labels[2].startswith("🟢")
    assert labels[3].startswith("🔴")
    assert len(labels[0]) <= 64
    for data in callbacks:
        assert len(data.encode("utf-8")) <= 64

    second = feedback_list_keyboard(
        kind=FeedbackKind.PROBLEM,
        items=[(uuid4(), FeedbackStatus.NEW, "одна")],
        offset=5,
        total=6,
    )
    second_callbacks = _callback_data(second)
    assert second_callbacks[0].startswith("fb_open:")
    assert "fb_list:problem:0" in second_callbacks
    assert "fb_list:problem:10" not in second_callbacks
    assert "home" in second_callbacks
    detail = _callback_data(feedback_detail_keyboard(FeedbackKind.IDEA))
    assert detail == ["fb_list:idea:0", "home"]


def test_moderator_keyboard_has_three_actions() -> None:
    ticket_id = uuid4()
    texts = _button_text(feedback_moderator_keyboard(ticket_id))
    assert texts == ["✅ Решено", "🟡 Взять в работу", "❌ Отменить"]
    callbacks = _callback_data(feedback_moderator_keyboard(ticket_id))
    assert callbacks == [f"fb_ok:{ticket_id}", f"fb_work:{ticket_id}", f"fb_no:{ticket_id}"]


def test_status_notice_for_idea_and_problem() -> None:
    assert author_status_text(kind=FeedbackKind.IDEA, status=FeedbackStatus.IN_PROGRESS, reply=None) == (
        "Твою идею взяли в работу. Когда будет что сказать — напишу сюда."
    )
    assert "решённым" in author_status_text(
        kind=FeedbackKind.PROBLEM,
        status=FeedbackStatus.RESOLVED,
        reply=None,
    )
    cancelled = author_status_text(kind=FeedbackKind.IDEA, status=FeedbackStatus.CANCELLED, reply="не сейчас")
    assert "Ответ: не сейчас" in cancelled
    assert feedback_list_label(FeedbackStatus.RESOLVED, "коротко").startswith("🟢")


def test_voice_is_allowed_for_the_whole_feedback_compose_session() -> None:
    assert voice_input_allowed(expected_input=ExpectedInput.FEEDBACK_TEXT, expected_field="idea")
    assert voice_input_allowed(expected_input=ExpectedInput.FEEDBACK_PHOTO, expected_field="idea")
