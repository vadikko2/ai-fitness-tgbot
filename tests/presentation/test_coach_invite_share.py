"""Native Telegram share URL for coach invite codes."""

from urllib.parse import parse_qs, unquote, urlparse

from fitness_bot.presentation.routers.coach import (
    _coach_share_code,
    _invite_share_button,
    _invite_share_url,
)


def test_coach_share_code_prefixes() -> None:
    assert _coach_share_code("abcd") == "c_ABCD"
    assert _coach_share_code("c_abcd") == "c_ABCD"


def test_invite_share_url_with_bot_username() -> None:
    url = _invite_share_url("c_ABCD1234", "my_fitness_bot")
    assert url.startswith("https://t.me/share/url?")
    query = parse_qs(urlparse(url).query)
    assert unquote(query["url"][0]) == "https://t.me/my_fitness_bot?start=c_ABCD1234"
    text = unquote(query["text"][0])
    assert text.startswith("c_ABCD1234")
    assert "Ввести код или ссылку" in text


def test_invite_share_url_without_username_uses_placeholder() -> None:
    url = _invite_share_url("c_ABCD1234", None)
    query = parse_qs(urlparse(url).query)
    assert unquote(query["url"][0]) == "https://t.me"
    assert unquote(query["text"][0]).startswith("c_ABCD1234")


def test_invite_share_button_is_url_type() -> None:
    button = _invite_share_button("c_ABCD1234", "my_fitness_bot")
    assert button.text == "📤 Отправить код"
    assert button.url is not None
    assert button.callback_data is None
    assert "t.me/share/url" in button.url
