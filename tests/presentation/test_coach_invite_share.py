"""Native Telegram share URL for coach invite codes."""

from urllib.parse import parse_qs, unquote, urlparse

from fitness_bot.presentation.routers.coach import (
    _INVITE_REGEN_STEPS,
    _coach_share_code,
    _invite_code_message,
    _invite_form_keyboard,
    _invite_join_start_payload,
    _invite_regen_confirm_keyboard,
    _invite_regen_confirm_text,
    _invite_share_button,
    _invite_share_text,
    _invite_share_url,
    _invite_token_from_start_payload,
    _is_own_invite_code,
)


def test_coach_share_code_prefixes() -> None:
    assert _coach_share_code("abcd") == "c_ABCD"
    assert _coach_share_code("c_abcd") == "c_ABCD"


def test_invite_token_from_start_payload() -> None:
    assert _invite_token_from_start_payload("c_abcd1234") == "c_ABCD1234"
    assert _invite_token_from_start_payload("join_c_abcd1234") == "c_ABCD1234"
    assert _invite_token_from_start_payload("join_ABCD1234") == "c_ABCD1234"
    assert _invite_token_from_start_payload("p_PROG") is None
    assert _invite_token_from_start_payload("") is None


def test_invite_join_start_payload() -> None:
    assert _invite_join_start_payload("c_ABCD1234") == "join_c_ABCD1234"
    assert _invite_join_start_payload("ABCD1234") == "join_c_ABCD1234"


def test_invite_code_message_uses_html_code_for_tap_copy() -> None:
    text = _invite_code_message("ABCD1234")
    assert "<code>c_ABCD1234</code>" in text
    assert "Нажми на код, чтобы скопировать." in text
    assert "Долгое нажатие" not in text
    regenerated = _invite_code_message("ABCD1234", regenerated=True)
    assert regenerated.startswith("Новый код приглашения:")
    assert "<code>c_ABCD1234</code>" in regenerated


def test_invite_share_text_has_coach_name_two_links_and_code() -> None:
    text = _invite_share_text("c_ABCD1234", "my_fitness_bot", coach_name="Анна")
    assert "Тренер «Анна» приглашает тебя в AI Fitness." in text
    assert "Ещё не в боте" in text
    assert "https://t.me/my_fitness_bot?start=c_ABCD1234" in text
    assert "Уже в боте" in text
    assert "https://t.me/my_fitness_bot?start=join_c_ABCD1234" in text
    assert "Ввести код или ссылку" in text
    assert "`c_ABCD1234`" in text


def test_invite_share_text_fallback_coach_name() -> None:
    text = _invite_share_text("c_ABCD1234", "bot", coach_name=None)
    assert "Тренер «тренер» приглашает тебя" in text


def test_invite_share_url_with_bot_username() -> None:
    url = _invite_share_url("c_ABCD1234", "my_fitness_bot", coach_name="Иван")
    assert url.startswith("https://t.me/share/url?")
    query = parse_qs(urlparse(url).query)
    # Preview URL is bot home; deep links live in text=.
    assert unquote(query["url"][0]) == "https://t.me/my_fitness_bot"
    text = unquote(query["text"][0])
    assert "Тренер «Иван»" in text
    assert "start=c_ABCD1234" in text
    assert "start=join_c_ABCD1234" in text
    assert "`c_ABCD1234`" in text
    assert "Ввести код или ссылку" in text


def test_invite_share_url_without_username_uses_placeholder() -> None:
    url = _invite_share_url("c_ABCD1234", None, coach_name="Анна")
    query = parse_qs(urlparse(url).query)
    assert unquote(query["url"][0]) == "https://t.me"
    text = unquote(query["text"][0])
    assert "Тренер «Анна»" in text
    assert "`c_ABCD1234`" in text


def test_invite_share_button_is_url_type() -> None:
    button = _invite_share_button("c_ABCD1234", "my_fitness_bot", coach_name="Анна")
    assert button.text == "📤 Отправить код"
    assert button.url is not None
    assert button.callback_data is None
    assert "t.me/share/url" in button.url


def test_invite_form_keyboard_has_share_back_home() -> None:
    kb = _invite_form_keyboard("c_ABCD1234", "my_fitness_bot", coach_name="Анна")
    rows = kb.inline_keyboard
    assert len(rows) == 3
    assert rows[0][0].text == "📤 Отправить код"
    assert rows[0][0].url is not None
    assert rows[1][0].text == "⬅️ Назад в кабинет"
    assert rows[1][0].callback_data == "coach_cab"
    assert rows[2][0].text == "🏠 В меню"
    assert rows[2][0].callback_data == "home"


def test_is_own_invite_code() -> None:
    assert _is_own_invite_code(raw_or_share="c_ABCD1234", cabinet_invite_code="ABCD1234")
    assert _is_own_invite_code(raw_or_share="abcd1234", cabinet_invite_code="ABCD1234")
    assert not _is_own_invite_code(raw_or_share="c_OTHER999", cabinet_invite_code="ABCD1234")
    assert not _is_own_invite_code(raw_or_share="c_ABCD1234", cabinet_invite_code=None)


def test_invite_regen_confirm_steps_do_not_regenerate_until_ok() -> None:
    """Steps 1–3 only advance; regenerate callback is coach_invite_new_ok."""
    assert set(_INVITE_REGEN_STEPS) == {1, 2, 3}
    assert _INVITE_REGEN_STEPS[1][2] == "coach_invite_new_2"
    assert _INVITE_REGEN_STEPS[2][2] == "coach_invite_new_3"
    assert _INVITE_REGEN_STEPS[3][2] == "coach_invite_new_ok"
    for step in (1, 2, 3):
        kb = _invite_regen_confirm_keyboard(step)
        rows = kb.inline_keyboard
        assert rows[0][0].text == _INVITE_REGEN_STEPS[step][1]
        assert rows[0][0].callback_data == _INVITE_REGEN_STEPS[step][2]
        assert rows[1][0].text == "❌ Отменить"
        assert rows[1][0].callback_data == "coach_invite_new_cancel"
        assert rows[2][0].text == "🏠 В кабинет"
        assert rows[2][0].callback_data == "coach_cab"
    # Only the final confirm callback triggers CreateCoachInviteCommand in the router.
    assert _invite_regen_confirm_keyboard(1).inline_keyboard[0][0].callback_data != "coach_invite_new_ok"
    assert _invite_regen_confirm_keyboard(2).inline_keyboard[0][0].callback_data != "coach_invite_new_ok"
    assert _invite_regen_confirm_keyboard(3).inline_keyboard[0][0].callback_data == "coach_invite_new_ok"


def test_invite_regen_confirm_texts_mention_risks() -> None:
    t1 = _invite_regen_confirm_text(1)
    assert "⚠️ Обновление кода" in t1
    assert "шаг" not in t1
    assert "⚠️ Старый код" in t1
    t2 = _invite_regen_confirm_text(2)
    assert "⚠️ Обновление кода" in t2
    assert "шаг" not in t2
    assert "привязанные" in t2
    assert "❗️" in t2
    t3 = _invite_regen_confirm_text(3)
    assert "⚠️ Обновление кода" in t3
    assert "шаг" not in t3
    assert "❗️" in t3
    assert "необратимо" in t3
