from __future__ import annotations

from fitness_bot.domain.enums import ExperienceLevel, ProfileField
from fitness_bot.domain.users.user import PROFILE_FIELD_ORDER
from fitness_bot.presentation.flow_helpers import experience_label
from fitness_bot.presentation.keyboards import PROFILE_FIELD_LABELS, profile_edit_keyboard
from fitness_bot.presentation.templates_env import create_jinja_env


def test_jinja_templates_do_not_escape_telegram_html() -> None:
    env = create_jinja_env()
    home = env.get_template("home.j2").render(
        age=31,
        weight_kg="90.00",
        goal="muscle_gain",
        goal_label="💪 Набор мышц",
    )
    assert "<b>🏠 Главное меню</b>" in home
    assert "• Возраст: <b>31</b>" in home
    assert "&lt;b&gt;" not in home

    profile = env.get_template("profile.j2").render(
        sex_label="🧔 Мужской",
        birth_year=1995,
        age=31,
        height_cm="185.0",
        weight_kg="90.00",
        experience_label=experience_label(ExperienceLevel.BEGINNER),
        experience_details="Три раза в неделю фуллбади в течение 2 месяцев",
        days_per_week=3,
        weekdays_label="Пн, Ср, Пт",
        equipment="Спортзал, все есть",
        training_place_label="🏋️ Зал",
        limitations_label="нет",
        activity_label="🚴 Умеренный",
        session_minutes=60,
        body_fat_label="не знаю",
        supplements_label="Нет",
        diet_prefs_label="нет",
        nutrition_constraints_label="нет",
        pharma_label="не принимаю",
        goal_label="💪 Набор мышц",
    )
    assert "<b>👤 Профиль</b>" in profile
    assert "• Год рождения: <b>1995</b>" in profile
    assert "• Опыт: <b>🌱 Новичок</b>" in profile
    assert "• Детали опыта: Три раза в неделю фуллбади в течение 2 месяцев" in profile
    assert "• Место занятий: <b>🏋️ Зал</b>" in profile
    assert "• Активность вне зала: <b>🚴 Умеренный</b>" in profile
    assert "• Длительность тренировки: <b>60 мин</b>" in profile
    assert "• % жира: <b>не знаю</b>" in profile
    assert "• Спортпит: Нет" in profile
    assert "• Пищевые предпочтения: нет" in profile
    assert "• Пищевые ограничения: нет" in profile
    assert "• Фарма / ПЭД: не принимаю" in profile
    assert "&lt;b&gt;" not in profile


def test_profile_edit_keyboard_includes_mvp_fields_and_pharma() -> None:
    markup = profile_edit_keyboard()
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    labels = [button.text for row in markup.inline_keyboard for button in row]

    for field in (
        ProfileField.ACTIVITY_LEVEL,
        ProfileField.SESSION_MINUTES,
        ProfileField.BODY_FAT,
        ProfileField.SUPPLEMENTS,
        ProfileField.DIET_PREFS,
        ProfileField.NUTRITION_CONSTRAINTS,
        ProfileField.TRAINING_PLACE,
        ProfileField.PHARMA,
        ProfileField.EXPERIENCE,
    ):
        assert f"prof_edit:{field.value}" in callbacks
        assert PROFILE_FIELD_LABELS[field] in labels

    assert "prof_edit:goal" in callbacks
    assert ProfileField.PHARMA not in PROFILE_FIELD_ORDER
    assert ProfileField.TRAINING_PLACE in PROFILE_FIELD_ORDER
    assert PROFILE_FIELD_ORDER.index(ProfileField.EQUIPMENT) < PROFILE_FIELD_ORDER.index(ProfileField.TRAINING_PLACE)
    assert PROFILE_FIELD_ORDER.index(ProfileField.DIET_PREFS) < PROFILE_FIELD_ORDER.index(
        ProfileField.NUTRITION_CONSTRAINTS,
    )


def test_pharma_prompt_leads_with_disclaimer() -> None:
    text = create_jinja_env().get_template("onboarding_prompt.j2").render(field="pharma")
    assert "Не рекомендуем" in text
    assert "<b>Не рекомендуем</b>" in text
    assert "&lt;b&gt;" not in text


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_body_tracking_moved_from_home_to_profile_hub() -> None:
    from fitness_bot.presentation.keyboards import home_keyboard, profile_hub_keyboard, profile_reminders_keyboard

    home = _callbacks(home_keyboard())
    for moved in ("wt_menu", "meas_menu", "pp_menu"):
        assert moved not in home
    assert {"profile", "feel", "hist", "sess_go", "prog"} <= set(home)

    hub = _callbacks(profile_hub_keyboard())
    assert hub[0] == "prof_form"
    assert {"wt_menu", "meas_menu", "pp_menu", "prof_remind", "prof_edit:height", "ihow:profile", "home"} <= set(hub)
    assert {"wt_remind", "pp_remind", "profile"} <= set(_callbacks(profile_reminders_keyboard()))


def test_body_screens_lead_back_to_profile() -> None:
    from fitness_bot.presentation.keyboards import (
        body_saved_keyboard,
        measurement_sites_keyboard,
        progress_photo_menu_keyboard,
        weight_menu_keyboard,
    )

    for markup in (
        profile_edit_keyboard(),
        weight_menu_keyboard(),
        measurement_sites_keyboard([("id", "Талия")]),
        progress_photo_menu_keyboard(),
        body_saved_keyboard(back_callback="wt_menu", back_label="⬅️ К весу"),
    ):
        callbacks = _callbacks(markup)
        assert "profile" in callbacks
        assert callbacks[-1] == "home"


def test_profile_hub_template_shows_last_weight_and_measurement_dates() -> None:
    from datetime import date

    text = (
        create_jinja_env()
        .get_template("profile_hub.j2")
        .render(
            profile_text="<b>👤 Профиль</b>",
            last_weight_kg="80.5",
            last_weight_on=date(2026, 10, 1),
            last_measurement_on=date(2026, 9, 20),
        )
    )
    assert "80.5 кг</b> · 01.10.2026" in text
    assert "последний замер 20.09.2026" in text
    empty = create_jinja_env().get_template("profile_hub.j2").render(profile_text="", last_weight_kg=None)
    assert "ещё не записан" in empty and "ещё не снимали" in empty
