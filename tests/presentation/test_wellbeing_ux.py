from __future__ import annotations

from datetime import date, datetime

from fitness_bot.presentation.keyboards import (
    history_menu_keyboard,
    program_screen_keyboard,
    session_rest_keyboard,
    session_template_keyboard,
    wellbeing_history_keyboard,
    wellbeing_saved_keyboard,
)
from fitness_bot.presentation.templates_env import create_jinja_env


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_adapt_button_is_always_on_day_preview_rest_day_and_week_plan() -> None:
    assert "feel_adapt_today" in _callbacks(session_template_keyboard())
    assert "feel_adapt_today" in _callbacks(session_template_keyboard(has_unapplied_wellbeing=True))
    assert "feel_adapt_week" in _callbacks(session_rest_keyboard())
    assert "feel_adapt_week" in _callbacks(program_screen_keyboard(has_pending=False, has_active=True))


def test_start_label_mentions_wellbeing_when_fresh_notes_exist() -> None:
    plain = session_template_keyboard().inline_keyboard[0][0]
    adapted = session_template_keyboard(has_unapplied_wellbeing=True).inline_keyboard[0][0]
    assert plain.callback_data == adapted.callback_data == "sess_plan"
    assert "самочувств" in adapted.text
    assert "самочувств" not in plain.text


def test_after_saving_wellbeing_offers_today_week_and_history() -> None:
    callbacks = _callbacks(wellbeing_saved_keyboard())
    assert callbacks[:3] == ["feel_adapt_today", "feel_adapt_week", "feel_hist:0"]
    assert "home" in callbacks


def test_history_menu_has_wellbeing_and_pagination() -> None:
    assert "feel_hist:0" in _callbacks(history_menu_keyboard())
    first = _callbacks(wellbeing_history_keyboard(offset=0, has_more=True))
    assert "feel_hist:10" in first
    middle = _callbacks(wellbeing_history_keyboard(offset=10, has_more=False))
    assert "feel_hist:0" in middle and "feel_hist:20" not in middle


def test_wellbeing_history_template_escapes_user_text_and_shows_status() -> None:
    env = create_jinja_env()
    text = env.get_template("wellbeing_history.j2").render(
        items=[
            {
                "text": "<b>болит</b>",
                "created_local": datetime(2026, 10, 17, 9, 30),
                "applied_on": date(2026, 10, 17),
                "is_fresh": False,
            },
            {"text": "устал", "created_local": datetime(2026, 10, 18, 8, 0), "applied_on": None, "is_fresh": True},
        ],
    )
    assert "&lt;b&gt;болит&lt;/b&gt;" in text
    assert "✅ учтено 17.10" in text
    assert "⏳ ещё не учтено" in text
