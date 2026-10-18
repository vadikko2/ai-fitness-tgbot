from fitness_bot.presentation.keyboards import (
    INFO_TOPIC_IDS,
    INFO_TOPICS,
    help_hub_keyboard,
    home_keyboard,
    info_menu_keyboard,
    info_offer_keyboard,
    info_topic_keyboard,
)
from fitness_bot.presentation.templates_env import create_jinja_env


def _callback_data(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_info_and_feedback_open_from_profile_help_hub() -> None:
    from fitness_bot.presentation.keyboards import profile_hub_keyboard

    home = _callback_data(home_keyboard())
    assert "help_hub" not in home
    assert "info" not in home
    assert "fb_menu:idea" not in home
    assert "fb_menu:problem" not in home
    assert "help_hub" in _callback_data(profile_hub_keyboard())
    assert _callback_data(help_hub_keyboard()) == ["info", "fb_menu:idea", "fb_menu:problem", "profile", "home"]
    menu = _callback_data(info_menu_keyboard())
    assert menu[-2:] == ["help_hub", "home"]
    text = create_jinja_env().get_template("help_hub.j2").render()
    assert "Инфо и связь" in text
    assert "&lt;" not in text
    menu_copy = create_jinja_env().get_template("info.j2").render(topic="menu")
    assert "«Профиль» → «Инфо и связь»" in menu_copy


def test_info_menu_lists_every_topic_and_returns_home() -> None:
    callbacks = _callback_data(info_menu_keyboard())
    assert callbacks[-1] == "home"
    topics = [item.removeprefix("info:") for item in callbacks if item.startswith("info:")]
    assert topics == [topic for topic, _label in INFO_TOPICS]
    assert set(topics) == INFO_TOPIC_IDS
    assert {"nutrition", "adapt", "share"} <= INFO_TOPIC_IDS
    for data in callbacks:
        assert len(data.encode("utf-8")) <= 64
    for _topic, label in INFO_TOPICS:
        assert len(label) <= 64


def test_info_topic_and_offer_keyboards() -> None:
    assert _callback_data(info_topic_keyboard()) == ["info", "home"]
    assert _callback_data(info_topic_keyboard(back="prog")) == ["prog", "home"]
    assert _callback_data(info_offer_keyboard()) == ["info", "home"]


def test_section_screens_open_matching_how_it_works() -> None:
    from fitness_bot.presentation.keyboards import (
        history_menu_keyboard,
        how_it_works_button,
        nutrition_current_keyboard,
        parse_how_it_works,
        profile_hub_keyboard,
        program_edit_menu_keyboard,
        program_screen_keyboard,
        session_template_keyboard,
        weight_menu_keyboard,
    )

    samples = {
        "prog": program_screen_keyboard(has_pending=False, has_active=True),
        "prog_edit_menu": program_edit_menu_keyboard(has_pending=False),
        "sess": session_template_keyboard(),
        "nutr": nutrition_current_keyboard(),
        "hist": history_menu_keyboard(),
        "wt_menu": weight_menu_keyboard(),
        "profile": profile_hub_keyboard(),
    }
    for origin, markup in samples.items():
        callbacks = _callback_data(markup)
        assert f"ihow:{origin}" in callbacks
        assert "home" in callbacks
        parsed = parse_how_it_works(f"ihow:{origin}")
        assert parsed is not None
        _topic, back = parsed
        assert back == origin
        assert len(f"ihow:{origin}".encode()) <= 64
    assert parse_how_it_works("ihow:nope") is None
    assert how_it_works_button("library").callback_data == "ihow:library"


def test_info_copy_renders_for_offer_menu_and_topics() -> None:
    env = create_jinja_env()
    template = env.get_template("info.j2")
    for topic in ("offer", "menu", *INFO_TOPIC_IDS):
        text = template.render(topic=topic).strip()
        assert text
        assert len(text) < 4096
        assert "<b>" in text
        assert "&lt;" not in text
    body = template.render(topic="body")
    assert "«Питание», «Самочувствие», «История», «Мой план сейчас», «Библиотека программ» и «Инфо и связь»" in body
    assert "лежит в «👤 Профиль»" in template.render(topic="history")
    assert "лежит в «👤 Профиль»" in template.render(topic="nutrition")
    assert "«Профиль» → «Инфо и связь»" in template.render(topic="menu")
    assert "Профиль → История → Самочувствие" in template.render(topic="adapt")
    assert "«Профиль» → «Библиотека программ»" in template.render(topic="share")
    assert "«Профиль»" in template.render(topic="offer")
    offer = template.render(topic="offer")
    assert "В меню — «Начать тренировку»." in offer
    assert "«Мой план сейчас»" in offer
    assert "и «Мой план сейчас»" not in offer
    plan = template.render(topic="plan")
    assert "лежит в «👤 Профиль»" in plan
    assert "В меню есть «Мой план сейчас»" not in plan
