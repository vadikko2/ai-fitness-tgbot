from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, Message
from jinja2 import Environment

from fitness_bot.domain.enums import ExpectedInput, ProfileField
from fitness_bot.presentation.keyboards import (
    ACTIVITY_LEVEL_LABELS,
    EXPERIENCE_LEVEL_LABELS,
    GOAL_LABELS,
    SEX_LABELS,
    SUPPLEMENT_LABELS,
    WEEKDAY_LABELS,
    activity_level_keyboard,
    body_fat_unknown_keyboard,
    diet_prefs_none_keyboard,
    experience_keyboard,
    goal_keyboard,
    home_keyboard,
    limitations_none_keyboard,
    profile_edit_keyboard,
    session_minutes_keyboard,
    sex_keyboard,
    supplements_keyboard,
    weekdays_keyboard,
)
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.users import GetHomeQuery, GetProfileQuery, GetProfileQueryResult

# Users who opened a field from the profile edit menu — save one field, then stop.
_PROFILE_EDIT_SESSION: set[int] = set()


def begin_profile_edit(telegram_user_id: int) -> None:
    _PROFILE_EDIT_SESSION.add(telegram_user_id)


def clear_profile_edit(telegram_user_id: int) -> None:
    _PROFILE_EDIT_SESSION.discard(telegram_user_id)


def profile_text(*, jinja_env: Environment, profile: GetProfileQueryResult) -> str:
    return jinja_env.get_template("profile.j2").render(
        sex_label=sex_label(profile.sex),
        birth_year=profile.birth_year,
        age=profile.age,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        experience_label=experience_label(profile.experience),
        experience_details=profile.experience_details,
        days_per_week=profile.days_per_week,
        weekdays_label=weekdays_label(profile.training_weekdays),
        equipment=profile.equipment,
        limitations_label=limitations_label(profile.limitations),
        activity_label=activity_label(profile.activity_level),
        session_minutes=profile.session_minutes,
        body_fat_label=body_fat_label(pct=profile.body_fat_pct, body_fat_set=profile.body_fat_set),
        supplements_label=supplements_label(profile.supplements, other=profile.supplements_other),
        diet_prefs_label=diet_prefs_label(profile.diet_prefs),
        pharma_label=pharma_label(profile.pharma),
        goal_label=goal_label(profile.goal),
    )


async def finish_profile_edit_if_active(
    *,
    message: Message,
    jinja_env: Environment,
    mediator,
    telegram_user_id: int,
) -> bool:
    """If this save came from profile edit, show profile and stop. Returns True when handled."""
    if telegram_user_id not in _PROFILE_EDIT_SESSION:
        return False
    clear_profile_edit(telegram_user_id)
    await mediator.send(
        ExpectInputCommand(
            telegram_user_id=telegram_user_id,
            expected_input=ExpectedInput.NONE,
        ),
    )
    profile = await mediator.send(GetProfileQuery(telegram_user_id=telegram_user_id))
    await message.answer(profile_text(jinja_env=jinja_env, profile=profile), reply_markup=profile_edit_keyboard())
    return True


def goal_label(value: object) -> str | None:
    if value is None:
        return None
    from fitness_bot.domain.enums import Goal

    return GOAL_LABELS.get(Goal(str(value)), str(value))


def sex_label(value: object) -> str | None:
    if value is None:
        return None
    from fitness_bot.domain.enums import Sex

    return SEX_LABELS.get(Sex(str(value)), str(value))


def experience_label(value: object) -> str | None:
    if value is None:
        return None
    from fitness_bot.domain.enums import ExperienceLevel

    try:
        return EXPERIENCE_LEVEL_LABELS.get(ExperienceLevel(str(value)), str(value))
    except ValueError:
        return str(value)


def activity_label(value: object) -> str | None:
    if value is None:
        return None
    from fitness_bot.domain.enums import ActivityLevel

    try:
        return ACTIVITY_LEVEL_LABELS.get(ActivityLevel(str(value)), str(value))
    except ValueError:
        return str(value)


def weekdays_label(days: list[int]) -> str:
    if not days:
        return ""
    return ", ".join(WEEKDAY_LABELS[day] for day in days)


def limitations_label(value: str | None) -> str:
    if value is None:
        return "—"
    if value == "":
        return "нет"
    return value


def diet_prefs_label(value: str | None) -> str:
    if value is None:
        return "—"
    if value == "":
        return "нет"
    return value


def supplements_label(codes: list[str] | None, *, other: str | None = None) -> str:
    if codes is None:
        return "—"
    from fitness_bot.domain.enums import Supplement

    parts: list[str] = []
    for code in codes:
        try:
            parts.append(SUPPLEMENT_LABELS[Supplement(code)])
        except ValueError:
            parts.append(code)
    text = ", ".join(parts) if parts else "—"
    if other:
        text = f"{text} ({other})" if text != "—" else other
    return text


def body_fat_label(*, pct: object, body_fat_set: bool) -> str:
    if not body_fat_set:
        return "—"
    if pct is None:
        return "не знаю"
    return f"{pct}%"


def pharma_label(value: str | None) -> str:
    if value is None:
        return "—"
    if value == "":
        return "не принимаю"
    return value


def markup_for_profile_field(
    field: ProfileField,
    *,
    days_per_week: int | None = None,
    selected_weekdays: set[int] | None = None,
    selected_supplements: set[str] | None = None,
) -> InlineKeyboardMarkup | None:
    if field == ProfileField.SEX:
        return sex_keyboard()
    if field == ProfileField.EXPERIENCE:
        return experience_keyboard()
    if field == ProfileField.TRAINING_WEEKDAYS:
        assert days_per_week is not None
        return weekdays_keyboard(selected_weekdays or set(), days_needed=days_per_week)
    if field == ProfileField.LIMITATIONS:
        return limitations_none_keyboard()
    if field == ProfileField.ACTIVITY_LEVEL:
        return activity_level_keyboard()
    if field == ProfileField.SESSION_MINUTES:
        return session_minutes_keyboard()
    if field == ProfileField.BODY_FAT:
        return body_fat_unknown_keyboard()
    if field == ProfileField.SUPPLEMENTS:
        return supplements_keyboard(selected_supplements or set())
    if field == ProfileField.DIET_PREFS:
        return diet_prefs_none_keyboard()
    return None


async def show_next_onboarding_step(
    *,
    message: Message,
    jinja_env: Environment,
    mediator,
    profile: GetProfileQueryResult,
    selected_weekdays: set[int] | None = None,
    selected_supplements: set[str] | None = None,
) -> None:
    if profile.profile_complete:
        home = await mediator.send(GetHomeQuery(telegram_user_id=profile.telegram_user_id))
        text = jinja_env.get_template("home.j2").render(
            age=home.age,
            weight_kg=home.weight_kg,
            goal=home.goal,
            goal_label=goal_label(home.goal),
        )
        await message.answer(text, reply_markup=home_keyboard())
        return
    if profile.next_field is None and profile.goal is None:
        text = jinja_env.get_template("onboarding_prompt.j2").render(field="goal", days_per_week=profile.days_per_week)
        await message.answer(text, reply_markup=goal_keyboard())
        return

    field = profile.next_field
    if field is None:
        return

    await mediator.send(
        ExpectInputCommand(
            telegram_user_id=profile.telegram_user_id,
            expected_input=ExpectedInput.PROFILE_FIELD,
            expected_field=field.value,
        ),
    )

    text = jinja_env.get_template("onboarding_prompt.j2").render(
        field=field.value,
        days_per_week=profile.days_per_week,
    )
    markup = markup_for_profile_field(
        field,
        days_per_week=profile.days_per_week,
        selected_weekdays=selected_weekdays or set(profile.training_weekdays),
        selected_supplements=selected_supplements
        if selected_supplements is not None
        else set(profile.supplements or ()),
    )
    await message.answer(text, reply_markup=markup)
