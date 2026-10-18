from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from fitness_bot.domain.enums import (
    ActivityLevel,
    ExperienceLevel,
    FeedbackKind,
    FeedbackStatus,
    Goal,
    ProfileField,
    Sex,
    Supplement,
    TrainingPlace,
)
from fitness_bot.domain.feedback.ticket import FEEDBACK_PAGE_SIZE
from fitness_bot.domain.program_catalog import (
    PROGRAM_TYPE_COPY,
    PROGRAM_TYPE_FREQUENT,
    PROGRAM_TYPE_SPECIAL,
    PROGRAM_TYPE_SPLITS,
    TRAINING_STYLE_COPY,
)
from fitness_bot.presentation.muscle_emoji import slot_nav_button_text

WEEKDAY_LABELS = {
    1: "Пн",
    2: "Вт",
    3: "Ср",
    4: "Чт",
    5: "Пт",
    6: "Сб",
    7: "Вс",
}

GOAL_LABELS = {
    Goal.FAT_LOSS: "🔥 Похудение",
    Goal.MUSCLE_GAIN: "💪 Набор мышц",
    Goal.STRENGTH: "🏋️ Сила",
    Goal.MAINTENANCE: "⚖️ Удержание веса",
    Goal.RECOVERY: "🧘 Восстановление",
    Goal.STAY_FIT: "✨ Поддержание формы",
    Goal.HEALTHY_LIFESTYLE: "🌿 Здоровый образ жизни",
}

SEX_LABELS = {
    Sex.MALE: "👨 Мужской",
    Sex.FEMALE: "👩 Женский",
}

ACTIVITY_LEVEL_LABELS = {
    ActivityLevel.SEDENTARY: "🪑 Сидячий",
    ActivityLevel.LIGHT: "🚶 Лёгкий",
    ActivityLevel.MODERATE: "🚴 Умеренный",
    ActivityLevel.HIGH: "🏃 Высокий",
}

EXPERIENCE_LEVEL_LABELS = {
    ExperienceLevel.BEGINNER: "🌱 Новичок",
    ExperienceLevel.INTERMEDIATE: "📈 Средний",
    ExperienceLevel.ADVANCED: "🏆 Продвинутый",
}

TRAINING_PLACE_LABELS = {
    TrainingPlace.GYM: "🏋️ Зал",
    TrainingPlace.HOME: "🏠 Дом",
    TrainingPlace.OUTDOOR: "🌳 Улица",
    TrainingPlace.MIXED: "🔀 Смешанно",
}

SUPPLEMENT_LABELS = {
    Supplement.NONE: "Нет",
    Supplement.PROTEIN: "Протеин",
    Supplement.CREATINE: "Креатин",
    Supplement.CAFFEINE_PREWORKOUT: "Кофеин / предтрен",
    Supplement.VITAMINS_OMEGA: "Витамины / омега",
    Supplement.OTHER: "Другое",
}

PROFILE_FIELD_LABELS = {
    ProfileField.SEX: "👤 Пол",
    ProfileField.BIRTH_YEAR: "🎂 Год рождения",
    ProfileField.HEIGHT: "📐 Рост",
    ProfileField.WEIGHT: "⚖️ Вес",
    ProfileField.EXPERIENCE: "📈 Опыт",
    ProfileField.EXPERIENCE_DETAILS: "📝 Детали опыта",
    ProfileField.DAYS_PER_WEEK: "🔢 Дней в неделю",
    ProfileField.TRAINING_WEEKDAYS: "📅 Дни тренировок",
    ProfileField.EQUIPMENT: "🛠️ Оборудование",
    ProfileField.TRAINING_PLACE: "📍 Место занятий",
    ProfileField.LIMITATIONS: "⚠️ Ограничения",
    ProfileField.ACTIVITY_LEVEL: "🚶 Активность вне зала",
    ProfileField.SESSION_MINUTES: "⏱ Длительность тренировки",
    ProfileField.BODY_FAT: "🧪 % жира",
    ProfileField.SUPPLEMENTS: "💊 Спортпит",
    ProfileField.DIET_PREFS: "🥗 Пищевые предпочтения",
    ProfileField.NUTRITION_CONSTRAINTS: "🚫 Пищевые ограничения",
    ProfileField.PHARMA: "💉 Фарма / ПЭД",
}

# Shown on profile edit keyboard (WEIGHT is logged separately).
_PROFILE_EDIT_FIELDS: tuple[ProfileField, ...] = (
    ProfileField.SEX,
    ProfileField.BIRTH_YEAR,
    ProfileField.HEIGHT,
    ProfileField.EXPERIENCE,
    ProfileField.EXPERIENCE_DETAILS,
    ProfileField.DAYS_PER_WEEK,
    ProfileField.TRAINING_WEEKDAYS,
    ProfileField.EQUIPMENT,
    ProfileField.TRAINING_PLACE,
    ProfileField.LIMITATIONS,
    ProfileField.ACTIVITY_LEVEL,
    ProfileField.SESSION_MINUTES,
    ProfileField.BODY_FAT,
    ProfileField.SUPPLEMENTS,
    ProfileField.DIET_PREFS,
    ProfileField.NUTRITION_CONSTRAINTS,
    ProfileField.PHARMA,
)

PROGRAM_TYPE_LABELS = {program_type.value: copy.label for program_type, copy in PROGRAM_TYPE_COPY.items()}
TRAINING_STYLE_LABELS = {style.value: copy.label for style, copy in TRAINING_STYLE_COPY.items()}

INTENSITY_LABELS = {
    "recovery": "восстановительная",
    "light": "легкая",
    "medium": "средняя",
    "heavy": "тяжелая",
}

_MENU = "🏠 В меню"
_TO_PROFILE = "⬅️ В профиль"
_BACK = "⬅️ Назад"
_CANCEL = "❌ Отмена"
_CONFIRM = "✅ Подтвердить"
_DONE = "✅ Готово"
_EDIT_TEXT = "✏️ Изменить текстом"
FEEL_ADAPT_LABEL = "🙂 Подстроить под самочувствие"
START_WORKOUT_LABEL = "▶️ Начать тренировку"
SIMILAR_EXERCISE_LABEL = "🔄 Похожее упражнение"
WELLBEING_HISTORY_PAGE_SIZE = 10


def home_keyboard(
    *,
    show_coach_badge: bool = False,
    active_clients_count: int = 0,
    is_moderator: bool = False,
    has_linked_coach: bool = False,
) -> InlineKeyboardMarkup:
    coach_btn = (
        InlineKeyboardButton(text="🧑‍🏫 Мой тренер", callback_data="coach_mine")
        if has_linked_coach
        else InlineKeyboardButton(text="🔎 Найти тренера", callback_data="coach_search")
    )
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=START_WORKOUT_LABEL, callback_data="sess_go")],
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            coach_btn,
        ],
    ]
    if show_coach_badge:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Кабинет тренера ({active_clients_count})",
                    callback_data="coach_cab",
                ),
            ],
        )
    else:
        rows.append([InlineKeyboardButton(text="Стать тренером", callback_data="coach_apply")])
    if is_moderator:
        rows.append([InlineKeyboardButton(text="🛡 Модератор", callback_data="mod")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sex_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=SEX_LABELS[Sex.MALE], callback_data="onb_sex:male"),
                InlineKeyboardButton(text=SEX_LABELS[Sex.FEMALE], callback_data="onb_sex:female"),
            ],
        ],
    )


def goal_keyboard(*, prefix: str = "onb_goal") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"{prefix}:{goal.value}")]
            for goal, label in GOAL_LABELS.items()
        ],
    )


def limitations_none_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👌 Нет ограничений", callback_data="onb_limits:none")]],
    )


def experience_keyboard(*, prefix: str = "onb_exp") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"{prefix}:{level.value}")]
            for level, label in EXPERIENCE_LEVEL_LABELS.items()
        ],
    )


def training_place_keyboard(*, prefix: str = "onb_place") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"{prefix}:{place.value}")]
            for place, label in TRAINING_PLACE_LABELS.items()
        ],
    )


def activity_level_keyboard(*, prefix: str = "onb_act") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"{prefix}:{level.value}")]
            for level, label in ACTIVITY_LEVEL_LABELS.items()
        ],
    )


def session_minutes_keyboard(*, prefix: str = "onb_mins") -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(text=f"{minutes} мин", callback_data=f"{prefix}:{minutes}") for minutes in (30, 45, 60, 90)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row[:2], row[2:]])


def body_fat_unknown_keyboard(*, prefix: str = "onb_bf") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🤷 Не знаю", callback_data=f"{prefix}:unknown")]],
    )


def diet_prefs_none_keyboard(*, prefix: str = "onb_diet") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👌 Без предпочтений", callback_data=f"{prefix}:none")]],
    )


def nutrition_constraints_none_keyboard(*, prefix: str = "onb_nconst") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👌 Нет ограничений", callback_data=f"{prefix}:none")]],
    )


def nutrition_current_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить план", callback_data="nutr_refresh")],
            [how_it_works_button("nutr")],
            [InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def supplements_keyboard(selected: set[str], *, prefix: str = "onb_supp") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for code, label in SUPPLEMENT_LABELS.items():
        mark = "✅ " if code.value in selected else ""
        rows.append(
            [InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"{prefix}:{code.value}")],
        )
    if selected:
        rows.append([InlineKeyboardButton(text=_DONE, callback_data=f"{prefix}:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pharma_keyboard(*, prefix: str = "prof_pharma") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Не принимаю", callback_data=f"{prefix}:none")],
            [InlineKeyboardButton(text="Укажу текстом", callback_data=f"{prefix}:text")],
            [InlineKeyboardButton(text=_BACK, callback_data="profile")],
        ],
    )


def weekdays_keyboard(selected: set[int], *, days_needed: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for day, label in WEEKDAY_LABELS.items():
        mark = "✅ " if day in selected else ""
        row.append(InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"onb_days:{day}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if len(selected) == days_needed:
        rows.append([InlineKeyboardButton(text=_DONE, callback_data="onb_days:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_edit_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=PROFILE_FIELD_LABELS[field], callback_data=f"prof_edit:{field.value}")]
        for field in _PROFILE_EDIT_FIELDS
    ]
    rows.append([InlineKeyboardButton(text="🎯 Цель", callback_data="prof_edit:goal")])
    rows.append([InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Анкета и цель", callback_data="prof_form")],
            [
                InlineKeyboardButton(text="⚖️ Вес", callback_data="wt_menu"),
                InlineKeyboardButton(text=PROFILE_FIELD_LABELS[ProfileField.HEIGHT], callback_data="prof_edit:height"),
            ],
            [InlineKeyboardButton(text="📏 Обхваты", callback_data="meas_menu")],
            [InlineKeyboardButton(text="📷 Фото прогресса", callback_data="pp_menu")],
            [InlineKeyboardButton(text="⏰ Напоминания", callback_data="prof_remind")],
            [
                InlineKeyboardButton(text="🥗 Питание", callback_data="nutr"),
                InlineKeyboardButton(text="🙂 Самочувствие", callback_data="feel"),
            ],
            [InlineKeyboardButton(text="📜 История", callback_data="hist")],
            [InlineKeyboardButton(text="📋 Мой план сейчас", callback_data="prog")],
            [InlineKeyboardButton(text="📚 Библиотека программ", callback_data="library")],
            [InlineKeyboardButton(text="ℹ️ Инфо и связь", callback_data="help_hub")],
            [how_it_works_button("profile")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def profile_reminders_keyboard(
    *,
    evening_enabled: bool = True,
    morning_enabled: bool = True,
) -> InlineKeyboardMarkup:
    evening = "🌙 Завтра тренировка: вкл" if evening_enabled else "🌙 Завтра тренировка: выкл"
    morning = "☀️ Сегодня тренировка: вкл" if morning_enabled else "☀️ Сегодня тренировка: выкл"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚖️ Напоминания о весе", callback_data="wt_remind")],
            [InlineKeyboardButton(text="📷 Напоминания о фото", callback_data="pp_remind")],
            [InlineKeyboardButton(text=evening, callback_data="tr_tog:evening")],
            [InlineKeyboardButton(text=morning, callback_data="tr_tog:morning")],
            [InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def training_reminder_keyboard(
    *,
    kind: Literal["evening", "morning"],
    target_date: date,
) -> InlineKeyboardMarkup:
    """Buttons on a training nudge.

    Evening «Да, завтра» prepares a draft the user confirms (``tr_yes``).
    Morning «Да» is the existing one-tap start (``sess_go``): generating a
    second draft in the morning would duplicate that flow.
    """
    iso = target_date.isoformat()
    if kind == "evening":
        yes = InlineKeyboardButton(text="✅ Да, завтра", callback_data=f"tr_yes:{iso}")
    else:
        yes = InlineKeyboardButton(text="✅ Да", callback_data="sess_go")
    skip = InlineKeyboardButton(text="🚫 Пропущу", callback_data=f"tr_skip:{iso}")
    return InlineKeyboardMarkup(inline_keyboard=[[yes, skip]])


def body_saved_keyboard(*, back_callback: str, back_label: str) -> InlineKeyboardMarkup:
    """After a weight / measurement save: back to that section, the profile hub, or home."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=back_label, callback_data=back_callback)],
            [InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def weight_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Записать вес", callback_data="wt_log")],
            [InlineKeyboardButton(text="📈 История", callback_data="wt_hist")],
            [InlineKeyboardButton(text="⏰ Расписание напоминаний", callback_data="wt_remind")],
            [how_it_works_button("wt_menu")],
            [InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def weight_reminder_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Раз в неделю (вс)", callback_data="wt_rm_preset:weekly")],
            [InlineKeyboardButton(text="🔁 Каждый день", callback_data="wt_rm_preset:daily")],
            [InlineKeyboardButton(text="🗓 Выбрать дни", callback_data="wt_rm_custom")],
            [InlineKeyboardButton(text="🕐 Изменить время", callback_data="wt_rm_time")],
            [InlineKeyboardButton(text="⬅️ К весу", callback_data="wt_menu")],
        ],
    )


def weight_reminder_weekdays_keyboard(selected: set[int]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for day, label in WEEKDAY_LABELS.items():
        mark = "✅ " if day in selected else ""
        row.append(InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"wt_rm_day:{day}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if selected:
        rows.append([InlineKeyboardButton(text=_DONE, callback_data="wt_rm_day:done")])
    rows.append([InlineKeyboardButton(text=_BACK, callback_data="wt_remind")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def weight_reminder_time_keyboard() -> InlineKeyboardMarkup:
    presets = ("08:00", "09:00", "10:00", "12:00", "18:00", "20:00")
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for value in presets:
        row.append(InlineKeyboardButton(text=f"🕐 {value}", callback_data=f"wt_rm_at:{value}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ Другое время", callback_data="wt_rm_at:custom")])
    rows.append([InlineKeyboardButton(text=_BACK, callback_data="wt_remind")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def history_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏋️ Тренировки", callback_data="hist_sess")],
            [InlineKeyboardButton(text="⚖️ Вес", callback_data="hist_wt")],
            [InlineKeyboardButton(text="📏 Обхваты", callback_data="hist_meas")],
            [InlineKeyboardButton(text="📷 Фото прогресса", callback_data="hist_pp")],
            [InlineKeyboardButton(text="🙂 Самочувствие", callback_data="feel_hist:0")],
            [how_it_works_button("hist")],
            [InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def progress_photo_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📷 Сфотографировать", callback_data="pp_log")],
            [InlineKeyboardButton(text="📈 История", callback_data="pp_hist")],
            [InlineKeyboardButton(text="⏰ Расписание напоминаний", callback_data="pp_remind")],
            [how_it_works_button("pp_menu")],
            [InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def progress_photo_reminder_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Раз в неделю (вс)", callback_data="pp_rm_preset:weekly")],
            [InlineKeyboardButton(text="🔁 Каждый день", callback_data="pp_rm_preset:daily")],
            [InlineKeyboardButton(text="🗓 Выбрать дни", callback_data="pp_rm_custom")],
            [InlineKeyboardButton(text="🕐 Изменить время", callback_data="pp_rm_time")],
            [InlineKeyboardButton(text="⬅️ К фото прогресса", callback_data="pp_menu")],
        ],
    )


def progress_photo_reminder_weekdays_keyboard(selected: set[int]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for day, label in WEEKDAY_LABELS.items():
        mark = "✅ " if day in selected else ""
        row.append(InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"pp_rm_day:{day}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if selected:
        rows.append([InlineKeyboardButton(text=_DONE, callback_data="pp_rm_day:done")])
    rows.append([InlineKeyboardButton(text=_BACK, callback_data="pp_remind")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def progress_photo_reminder_time_keyboard() -> InlineKeyboardMarkup:
    presets = ("08:00", "09:00", "10:00", "12:00", "18:00", "20:00")
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for value in presets:
        row.append(InlineKeyboardButton(text=f"🕐 {value}", callback_data=f"pp_rm_at:{value}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ Другое время", callback_data="pp_rm_at:custom")])
    rows.append([InlineKeyboardButton(text=_BACK, callback_data="pp_remind")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def progress_photo_history_keyboard(
    *,
    items: list[tuple[str, str]],
    offset: int,
    has_more: bool,
    subject_user_id: str | None = None,
    back_callback: str = "pp_menu",
) -> InlineKeyboardMarkup:
    """Date buttons for progress-photo history. ``items`` are (set_id, label)."""
    if subject_user_id is None:
        one_prefix = "pp_hist_one"
        list_prefix = "pp_hist"
    else:
        # Coach drill-down uses set id only (≤64 bytes); authz resolves owner in the handler.
        one_prefix = "coach_pp_one"
        list_prefix = f"coach_pp_hist:{subject_user_id}"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=label[:64], callback_data=f"{one_prefix}:{set_id}")] for set_id, label in items
    ]
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        prev_offset = max(0, offset - 10)
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{list_prefix}:{prev_offset}"))
    if has_more:
        nav.append(InlineKeyboardButton(text="Ещё ➡️", callback_data=f"{list_prefix}:{offset + 10}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=_BACK, callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coach_mine_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔓 Отвязать", callback_data="coach_mine_unlink")],
            [InlineKeyboardButton(text="🔎 Сменить / найти другого", callback_data="coach_search")],
            [how_it_works_button("coach_mine")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def session_history_keyboard(
    *,
    items: list[tuple[str, str]],
    offset: int,
    has_more: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=f"📌 {title}"[:64], callback_data=f"hist_one:{session_id}")]
        for session_id, title in items
    ]
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        prev_offset = max(0, offset - 10)
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"hist_sess:{prev_offset}"))
    if has_more:
        nav.append(InlineKeyboardButton(text="Ещё ➡️", callback_data=f"hist_sess:{offset + 10}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="📜 К истории", callback_data="hist")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def history_session_keyboard(*, watch_items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"🎥 Посмотреть видео · {label}"[:64],
                callback_data=f"hist_vid:{slot_id}",
            ),
        ]
        for slot_id, label in watch_items
    ]
    rows.append([InlineKeyboardButton(text="📋 К списку", callback_data="hist_sess")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coach_session_history_keyboard(
    *,
    client_user_id: str,
    items: list[tuple[str, str]],
    offset: int,
    has_more: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=f"📌 {title}"[:64], callback_data=f"coach_hist_one:{client_user_id}:{session_id}")]
        for session_id, title in items
    ]
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        prev_offset = max(0, offset - 10)
        nav.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"coach_hist:{client_user_id}:{prev_offset}",
            ),
        )
    if has_more:
        nav.append(
            InlineKeyboardButton(
                text="Ещё ➡️",
                callback_data=f"coach_hist:{client_user_id}:{offset + 10}",
            ),
        )
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ К клиенту", callback_data=f"coach_client:{client_user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coach_history_session_keyboard(
    *,
    client_user_id: str,
    watch_items: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"🎥 Посмотреть видео · {label}"[:64],
                callback_data=f"coach_hist_vid:{client_user_id}:{slot_id}",
            ),
        ]
        for slot_id, label in watch_items
    ]
    rows.append([InlineKeyboardButton(text="📋 К списку", callback_data=f"coach_hist:{client_user_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ К клиенту", callback_data=f"coach_client:{client_user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coach_recent_videos_keyboard(
    *,
    client_user_id: str,
    items: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"🎥 {label}"[:64],
                callback_data=f"coach_hist_vid:{client_user_id}:{slot_id}",
            ),
        ]
        for slot_id, label in items
    ]
    rows.append([InlineKeyboardButton(text="⬅️ К клиенту", callback_data=f"coach_client:{client_user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coach_apply_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Подать заявку", callback_data="coach_apply_start")],
            [InlineKeyboardButton(text="📋 Мои заявки", callback_data="coach_apps")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def coach_apps_keyboard(*, items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"coach_app:{app_id}")] for app_id, label in items]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="coach_apply")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coach_app_detail_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К заявкам", callback_data="coach_apps")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def coach_apply_submitted_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои заявки", callback_data="coach_apps")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def coach_application_approved_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Кабинет тренера", callback_data="coach_cab")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def coach_application_rejected_keyboard(*, application_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Посмотреть заявку", callback_data=f"coach_app:{application_id}")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def coach_client_proposal_keyboard(*, client_user_id: str, can_approve: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="✏️ Ещё правка текстом", callback_data=f"coach_edit:{client_user_id}")],
    ]
    if can_approve:
        rows.append(
            [InlineKeyboardButton(text="✅ Применить клиенту", callback_data=f"coach_prog_ok:{client_user_id}")],
        )
    rows.append(
        [InlineKeyboardButton(text="❌ Отменить правку", callback_data=f"coach_prog_cancel:{client_user_id}")],
    )
    rows.append([InlineKeyboardButton(text="⬅️ К клиенту", callback_data=f"coach_client:{client_user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def measurement_sites_keyboard(sites: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"📍 {name}", callback_data=f"meas_site:{site_id}")] for site_id, name in sites]
    rows.append([InlineKeyboardButton(text="➕ Своя точка", callback_data="meas_custom")])
    rows.append([how_it_works_button("meas_menu")])
    rows.append([InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


INFO_TOPICS: tuple[tuple[str, str], ...] = (
    ("plan", "📋 Как собрать план"),
    ("edit", "✏️ Как изменить план"),
    ("share", "📤 Поделиться планом"),
    ("session", "▶️ Как пройти тренировку"),
    ("workout", "💪 Правка дня и техника"),
    ("adapt", "🔄 Как подстраивается"),
    ("nutrition", "🥗 Питание"),
    ("history", "📜 История прогресса"),
    ("body", "📏 Вес, обхваты, напоминания"),
    ("coach", "🔎 Тренер"),
    ("cabinet", "🧑‍🏫 Кабинет тренера"),
)
INFO_TOPIC_IDS = frozenset(topic for topic, _label in INFO_TOPICS)

# Section entry callback → info article. Back from the article reopens this callback.
SECTION_INFO_ORIGIN: dict[str, str] = {
    "prog": "plan",
    "prog_edit_menu": "edit",
    "library": "share",
    "sess": "session",
    "sess_go": "session",
    "sess_tmpl_edit": "workout",
    "nutr": "nutrition",
    "hist": "history",
    "wt_menu": "body",
    "meas_menu": "body",
    "pp_menu": "body",
    "profile": "body",
    "coach_search": "coach",
    "coach_mine": "coach",
    "coach_cab": "cabinet",
}
_HOW_IT_WORKS = "❓ Как это работает"


def how_it_works_button(origin: str) -> InlineKeyboardButton:
    if origin not in SECTION_INFO_ORIGIN:
        raise KeyError(origin)
    return InlineKeyboardButton(text=_HOW_IT_WORKS, callback_data=f"ihow:{origin}")


def parse_how_it_works(data: str) -> tuple[str, str] | None:
    """Return (info topic, back callback) for a how-it-works press."""
    origin = data.removeprefix("ihow:")
    if origin == data or origin not in SECTION_INFO_ORIGIN:
        return None
    return SECTION_INFO_ORIGIN[origin], origin


def help_hub_keyboard() -> InlineKeyboardMarkup:
    """Info, idea, and problem. Handlers stay separate; this is only the entry."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="ℹ️ Инфо", callback_data="info")],
            [InlineKeyboardButton(text="💡 Есть идея", callback_data="fb_menu:idea")],
            [InlineKeyboardButton(text="⚠️ Сообщить о проблеме", callback_data="fb_menu:problem")],
            [InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def info_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"info:{topic}")] for topic, label in INFO_TOPICS]
    rows.append([InlineKeyboardButton(text=_BACK, callback_data="help_hub")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def info_topic_keyboard(*, back: str = "info") -> InlineKeyboardMarkup:
    back_label = "⬅️ Назад" if back != "info" else "⬅️ К разделам"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=back_label, callback_data=back)],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def info_offer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="ℹ️ Инфо", callback_data="info")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=_MENU, callback_data="home")]])


def stub_later_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=_MENU, callback_data="home")]])


def program_type_keyboard() -> InlineKeyboardMarkup:
    frequent = [
        InlineKeyboardButton(
            text=PROGRAM_TYPE_COPY[program_type].label,
            callback_data=f"prog_type:{program_type.value}",
        )
        for program_type in PROGRAM_TYPE_FREQUENT
    ]
    splits = [
        InlineKeyboardButton(
            text=PROGRAM_TYPE_COPY[program_type].label,
            callback_data=f"prog_type:{program_type.value}",
        )
        for program_type in PROGRAM_TYPE_SPLITS
    ]
    special = [
        InlineKeyboardButton(
            text=PROGRAM_TYPE_COPY[program_type].label,
            callback_data=f"prog_type:{program_type.value}",
        )
        for program_type in PROGRAM_TYPE_SPECIAL
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            frequent,
            splits,
            special[:2],
            special[2:],
            [how_it_works_button("prog")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def program_after_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Описать текстом или голосом", callback_data="prog_text")],
            [InlineKeyboardButton(text="✨ Пусть предложит", callback_data="prog_gen")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def proposal_actions_keyboard(
    *,
    can_approve: bool,
    days: list[tuple[int, str]] | None = None,
    can_save_to_library: bool = False,
) -> InlineKeyboardMarkup:
    """days: list of (day_position, button_label)."""
    rows: list[list[InlineKeyboardButton]] = []
    for position, label in days or []:
        rows.append(
            [InlineKeyboardButton(text=f"📅 {label}"[:64], callback_data=f"prog_day:{position}")],
        )
    rows.append([InlineKeyboardButton(text="✏️ Изменить текстом или голосом", callback_data="prog_edit")])
    if can_save_to_library:
        rows.append(
            [InlineKeyboardButton(text="📚 Сохранить в библиотеку", callback_data="prog_lib_save")],
        )
    if can_approve:
        rows.append([InlineKeyboardButton(text="✅ Сделать активной", callback_data="prog_ok")])
    rows.append([InlineKeyboardButton(text="❌ Отменить черновик", callback_data="draft_cancel")])
    rows.append([InlineKeyboardButton(text="📋 К программе", callback_data="prog")])
    rows.append([how_it_works_button("prog")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def proposal_day_keyboard(
    *,
    day_position: int,
    slots: list[tuple[int, str]] | None = None,
) -> InlineKeyboardMarkup:
    """Day constructor: per-exercise buttons; program activate stays on week draft only.

    slots: (slot_position, exercise_label).
    """
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=slot_nav_button_text(position=item[0], label=item[1]),
                callback_data=f"pdraft_slot:{day_position}:{item[0]}",
            ),
        ]
        for item in slots or []
    ]
    rows.append([InlineKeyboardButton(text="📅 К черновику", callback_data="prog_draft")])
    rows.append(
        [InlineKeyboardButton(text="✏️ Изменить текстом или голосом", callback_data=f"prog_edit_day:{day_position}")],
    )
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def proposal_slot_keyboard(
    *,
    day_position: int,
    slot_position: int,
    has_catalog_guide: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="✏️ Вес и повторы",
                callback_data=f"pdraft_edit:{day_position}:{slot_position}",
            ),
        ],
    ]
    if has_catalog_guide:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📖 Как делать",
                    callback_data=f"pdraft_how:{day_position}:{slot_position}",
                ),
            ],
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ К тренировке", callback_data=f"prog_day:{day_position}")],
    )
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def proposal_slot_weight_keyboard(
    *,
    day_position: int,
    slot_position: int,
    planned_weight_kg: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if planned_weight_kg:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ Как в плане · {planned_weight_kg} кг",
                    callback_data=f"pdraft_w_plan:{day_position}:{slot_position}",
                ),
            ],
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="⚪ Без веса",
                callback_data=f"pdraft_w_none:{day_position}:{slot_position}",
            ),
        ],
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"pdraft_slot:{day_position}:{slot_position}",
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def proposal_slot_load_keyboard(
    *,
    day_position: int,
    slot_position: int,
    planned_label: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if planned_label:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ Как в плане · {planned_label}",
                    callback_data=f"pdraft_r_plan:{day_position}:{slot_position}",
                ),
            ],
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ К весу",
                callback_data=f"pdraft_edit:{day_position}:{slot_position}",
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def match_exercises_keyboard(
    *,
    day_position: int,
    slot_position: int,
    items: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"💪 {name}"[:60],
                callback_data=f"prog_pick:{day_position}:{slot_position}:{exercise_id}",
            ),
        ]
        for exercise_id, name in items
    ]
    rows.append([InlineKeyboardButton(text=_EDIT_TEXT, callback_data="prog_edit")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def program_screen_keyboard(
    *,
    has_pending: bool,
    has_active: bool,
    days: list[tuple[int, str]] | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for position, label in days or []:
        rows.append(
            [InlineKeyboardButton(text=f"📅 {label}"[:64], callback_data=f"prog_view_day:{position}")],
        )
    if has_active:
        rows.append([InlineKeyboardButton(text="🗓 Сегодня по плану (без старта)", callback_data="sess")])
    rows.append([InlineKeyboardButton(text="✏️ Изменить программу", callback_data="prog_edit_menu")])
    if has_active:
        rows.append([InlineKeyboardButton(text=FEEL_ADAPT_LABEL, callback_data="feel_adapt_week")])
        rows.append(
            [
                InlineKeyboardButton(
                    text="📚 Сохранить в библиотеку",
                    callback_data="prog_lib_save_active",
                ),
            ],
        )
    if has_pending:
        rows.append([InlineKeyboardButton(text="📝 Есть черновик — открыть", callback_data="prog_draft")])
    rows.append([how_it_works_button("prog")])
    rows.append([InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def program_edit_menu_keyboard(*, has_pending: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_pending:
        rows.append([InlineKeyboardButton(text="📝 Открыть черновик", callback_data="prog_draft")])
    rows.append([InlineKeyboardButton(text="🔄 Задать / сменить программу", callback_data="prog_setup")])
    rows.append([InlineKeyboardButton(text="📋 К программе", callback_data="prog")])
    rows.append([how_it_works_button("prog_edit_menu")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def program_day_keyboard(
    *,
    day_position: int,
    slots: list[tuple[int, str]] | None = None,
) -> InlineKeyboardMarkup:
    """slots: (slot_position, exercise_label)."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=slot_nav_button_text(position=item[0], label=item[1]),
                callback_data=f"prog_view_slot:{day_position}:{item[0]}",
            ),
        ]
        for item in slots or []
    ]
    rows.append([InlineKeyboardButton(text="📋 К программе", callback_data="prog")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def program_slot_keyboard(
    *,
    day_position: int,
    slot_position: int,
    has_catalog_guide: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_catalog_guide:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📖 Как делать",
                    callback_data=f"prog_view_how:{day_position}:{slot_position}",
                ),
            ],
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ К дню", callback_data=f"prog_view_day:{day_position}")],
    )
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def exercise_guide_keyboard(
    *,
    videos: list[tuple[str, str, str]],
    back_callback: str,
) -> InlineKeyboardMarkup:
    """videos: (platform, url, title). Opens Rutube/YouTube via Telegram URL buttons."""
    rows: list[list[InlineKeyboardButton]] = []
    for index, (platform, url, title) in enumerate(videos[:5], start=1):
        platform_label = "Rutube" if platform == "rutube" else "YouTube" if platform == "youtube" else platform
        label = f"🎥 {platform_label}: {title or f'видео {index}'}"[:64]
        rows.append([InlineKeyboardButton(text=label, url=url)])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_template_keyboard(
    *,
    week_finished: bool = False,
    has_unapplied_wellbeing: bool = False,
) -> InlineKeyboardMarkup:
    start_label = "▶️ Начать с учётом самочувствия" if has_unapplied_wellbeing else "▶️ Начать как в плане"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=start_label, callback_data="sess_plan")],
        [InlineKeyboardButton(text="✏️ Изменить тренировку", callback_data="sess_tmpl_edit")],
        [InlineKeyboardButton(text=FEEL_ADAPT_LABEL, callback_data="feel_adapt_today")],
    ]
    new_week_label = "🆕 Начать новую тренировочную неделю"
    if week_finished:
        rows.insert(0, [InlineKeyboardButton(text=new_week_label, callback_data="sess_new_week")])
    else:
        rows.append([InlineKeyboardButton(text=new_week_label, callback_data="sess_new_week")])
    rows.append([how_it_works_button("sess")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_template_edit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Написать что поменять", callback_data="sess_tmpl_edit_text")],
            [InlineKeyboardButton(text="✨ Перегенерировать по истории", callback_data="sess_gen")],
            [InlineKeyboardButton(text="⬅️ Назад к плану", callback_data="sess")],
            [how_it_works_button("sess_tmpl_edit")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def session_repeat_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Повторить", callback_data="sess_plan_repeat")],
            [InlineKeyboardButton(text=_CANCEL, callback_data="sess")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def next_session_actions_keyboard(*, can_approve: bool, offer_plain_start: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_approve:
        rows.append([InlineKeyboardButton(text=_CONFIRM, callback_data="sess_gen_ok")])
    if offer_plain_start:
        rows.append([InlineKeyboardButton(text="▶️ Начать как в плане, без учёта", callback_data="sess_plan_raw")])
    rows.append([InlineKeyboardButton(text=_CANCEL, callback_data="draft_cancel")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def nutrition_no_program_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Программа", callback_data="prog")],
            [how_it_works_button("nutr")],
            [InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def session_exercise_actions_keyboard(*, position: int) -> InlineKeyboardMarkup:
    """Actions on one exercise message. The guide button is omitted: technique is in the text."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Как в плане → дальше", callback_data=f"slot_plan:{position}")],
            [InlineKeyboardButton(text="✏️ Вес и повторы", callback_data=f"slot_fact:{position}")],
            [InlineKeyboardButton(text=SIMILAR_EXERCISE_LABEL, callback_data=f"slot_alt:{position}")],
        ],
    )


def session_pack_closer_keyboard() -> InlineKeyboardMarkup:
    """After the exercise pack: log the rest as planned, or finish only what is already logged."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Выполнить все", callback_data="sess_plan_all")],
            [InlineKeyboardButton(text="Завершить тренировку", callback_data="sess_fin")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def session_continue_keyboard(
    *,
    next_position: int | None = None,
    next_label: str | None = None,
) -> InlineKeyboardMarkup:
    """One next exercise to log, or «Готово» when every set is already written. Plus the menu."""
    rows: list[list[InlineKeyboardButton]] = []
    label = (next_label or "").strip()
    if next_position is not None and label:
        rows.append(
            [InlineKeyboardButton(text=label[:64], callback_data=f"slot:{next_position}")],
        )
    else:
        rows.append([InlineKeyboardButton(text=_DONE, callback_data="sess_fin")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_card_keyboard(
    *,
    slots: list[tuple[int, str]] | None = None,
    has_unapplied_wellbeing: bool = False,
) -> InlineKeyboardMarkup:
    """slots: (slot_position, exercise_label)."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=slot_nav_button_text(position=item[0], label=item[1]),
                callback_data=f"slot:{item[0]}",
            ),
        ]
        for item in slots or []
    ]
    if has_unapplied_wellbeing:
        rows.append([InlineKeyboardButton(text=FEEL_ADAPT_LABEL, callback_data="feel_adapt_today")])
    rows.append([InlineKeyboardButton(text="✏️ Изменить", callback_data="sess_edit")])
    rows.append([InlineKeyboardButton(text="🏁 Выполнить всю тренировку", callback_data="sess_all")])
    rows.append([InlineKeyboardButton(text="🔄 Начать заново", callback_data="sess_restart")])
    rows.append([how_it_works_button("sess")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_restart_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Начать заново", callback_data="sess_restart_ok")],
            [InlineKeyboardButton(text=_CANCEL, callback_data="sess")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def slot_actions_keyboard(
    *,
    position: int,
    has_actual: bool = False,
    has_technique_video: bool = False,
    has_catalog_guide: bool = False,
    can_swap: bool = False,
    swapped_from: tuple[str, str] | None = None,
    offer_program_swap: bool = False,
) -> InlineKeyboardMarkup:
    """swapped_from: (exercise_id, name) of the exercise replaced just now — offers «Вернуть»."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="✅ Как в плане → дальше", callback_data=f"slot_plan:{position}")],
        [InlineKeyboardButton(text="✏️ Вес и повторы", callback_data=f"slot_fact:{position}")],
    ]
    if can_swap:
        rows.append([InlineKeyboardButton(text=SIMILAR_EXERCISE_LABEL, callback_data=f"slot_alt:{position}")])
    if offer_program_swap:
        rows.append(
            [InlineKeyboardButton(text="📋 Заменить и в программе", callback_data=f"slot_swap_prog:{position}")],
        )
    if swapped_from is not None:
        old_id, old_name = swapped_from
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"↩️ Вернуть «{old_name}»"[:64],
                    callback_data=f"slot_swap:{position}:{old_id}",
                ),
            ],
        )
    if has_catalog_guide:
        rows.append([InlineKeyboardButton(text="📖 Как делать", callback_data=f"slot_how:{position}")])
    if has_actual:
        label = "🎥 Заменить своё видео" if has_technique_video else "🎥 Загрузить видео упражнения"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"slot_video:{position}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад к тренировке", callback_data="sess")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_slot_keyboard(*, position: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К упражнению", callback_data=f"slot:{position}")],
            [InlineKeyboardButton(text="⬅️ Назад к тренировке", callback_data="sess")],
        ],
    )


def similar_exercises_keyboard(
    *,
    position: int,
    items: list[tuple[str, str]],
    next_offset: int | None = None,
) -> InlineKeyboardMarkup:
    """items: (exercise_id, name)."""
    rows = [
        [InlineKeyboardButton(text=f"💪 {name}"[:64], callback_data=f"slot_swap:{position}:{exercise_id}")]
        for exercise_id, name in items
    ]
    if next_offset is not None:
        rows.append([InlineKeyboardButton(text="🔁 Ещё варианты", callback_data=f"slot_alt:{position}:{next_offset}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"slot:{position}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def slot_weight_keyboard(*, position: int, planned_weight_kg: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if planned_weight_kg:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ Как в плане · {planned_weight_kg} кг",
                    callback_data=f"slot_w_plan:{position}",
                ),
            ],
        )
    rows.append([InlineKeyboardButton(text="⚪ Без веса", callback_data=f"slot_w_none:{position}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"slot:{position}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def slot_load_keyboard(
    *,
    position: int,
    planned_label: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if planned_label:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ Как в плане · {planned_label}",
                    callback_data=f"slot_r_plan:{position}",
                ),
            ],
        )
    rows.append([InlineKeyboardButton(text="⬅️ К весу", callback_data=f"slot_fact:{position}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def performance_actions_keyboard(*, can_approve: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_approve:
        rows.append([InlineKeyboardButton(text="✅ Подтвердить факт", callback_data="slot_ok")])
    rows.append([InlineKeyboardButton(text=_CANCEL, callback_data="draft_cancel")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def completion_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_DONE, callback_data="sess_fin")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def completion_deviation_actions_keyboard(*, can_approve: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_approve:
        rows.append([InlineKeyboardButton(text="🏁 Подтвердить и завершить", callback_data="sess_fin_ok")])
    rows.append([InlineKeyboardButton(text="✅ Готово без правок", callback_data="sess_fin")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_no_program_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Программа", callback_data="prog")],
            [how_it_works_button("sess")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def _train_anyway_button(alternative: tuple[int, str]) -> InlineKeyboardButton:
    weekday, title = alternative
    day_label = WEEKDAY_LABELS.get(weekday, str(weekday))
    return InlineKeyboardButton(
        text=f"💪 Всё равно потренироваться: {day_label} · {title}"[:64],
        callback_data=f"sess_go_day:{weekday}",
    )


def session_rest_keyboard(
    *,
    week_finished: bool = False,
    alternative: tuple[int, str] | None = None,
) -> InlineKeyboardMarkup:
    """alternative: (weekday, day title) of the nearest not-completed program day."""
    rows: list[list[InlineKeyboardButton]] = []
    if alternative is not None:
        rows.append([_train_anyway_button(alternative)])
    new_week = [InlineKeyboardButton(text="🆕 Начать новую тренировочную неделю", callback_data="sess_new_week")]
    if week_finished:
        rows.append(new_week)
        rows.append([InlineKeyboardButton(text="📜 История", callback_data="hist")])
    else:
        rows.append([InlineKeyboardButton(text="📜 История", callback_data="hist")])
        rows.append(new_week)
    rows.append([InlineKeyboardButton(text=FEEL_ADAPT_LABEL, callback_data="feel_adapt_week")])
    rows.append([how_it_works_button("sess")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_done_today_keyboard(
    *,
    weekday: int | None = None,
    alternative: tuple[int, str] | None = None,
) -> InlineKeyboardMarkup:
    repeat = f"sess_plan_repeat:{weekday}" if weekday else "sess_plan_repeat"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🔄 Повторить", callback_data=repeat)],
    ]
    if alternative is not None:
        weekday_alt, title = alternative
        day_label = WEEKDAY_LABELS.get(weekday_alt, str(weekday_alt))
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"💪 Ещё одну: {day_label} · {title}"[:64],
                    callback_data=f"sess_go_day:{weekday_alt}",
                ),
            ],
        )
    rows.append([InlineKeyboardButton(text="📋 План недели", callback_data="prog")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def workout_edit_actions_keyboard(*, can_approve: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=_EDIT_TEXT, callback_data="sess_edit")],
    ]
    if can_approve:
        rows.append([InlineKeyboardButton(text=_CONFIRM, callback_data="sess_edit_ok")])
    rows.append([InlineKeyboardButton(text=_CANCEL, callback_data="draft_cancel")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def match_session_exercises_keyboard(
    *,
    slot_position: int,
    items: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"💪 {name}"[:60],
                callback_data=f"sess_pick:{slot_position}:{exercise_id}",
            ),
        ]
        for exercise_id, name in items
    ]
    rows.append([InlineKeyboardButton(text=_EDIT_TEXT, callback_data="sess_edit")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


_FEEDBACK_MARK = {
    FeedbackStatus.NEW: "⚪️",
    FeedbackStatus.IN_PROGRESS: "🟡",
    FeedbackStatus.RESOLVED: "🟢",
    FeedbackStatus.CANCELLED: "🔴",
}

_FEEDBACK_WRITE = {
    FeedbackKind.IDEA: "✍️ Предложить идею",
    FeedbackKind.PROBLEM: "✍️ Описать проблему",
}
_FEEDBACK_MINE = {
    FeedbackKind.IDEA: "📋 Мои идеи",
    FeedbackKind.PROBLEM: "📋 Мои сообщения",
}


def feedback_status_mark(status: FeedbackStatus) -> str:
    return _FEEDBACK_MARK[status]


def feedback_list_label(status: FeedbackStatus, body: str) -> str:
    preview = " ".join(body.split())
    if len(preview) > 32:
        preview = preview[:31] + "…"
    return f"{feedback_status_mark(status)} {preview}"


def feedback_menu_keyboard(kind: FeedbackKind) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_FEEDBACK_WRITE[kind], callback_data=f"fb_new:{kind.value}")],
            [InlineKeyboardButton(text=_FEEDBACK_MINE[kind], callback_data=f"fb_list:{kind.value}:0")],
            [InlineKeyboardButton(text=_BACK, callback_data="help_hub")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def feedback_compose_keyboard(ticket_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Отправить", callback_data=f"fb_send:{ticket_id}")],
            [InlineKeyboardButton(text=_CANCEL, callback_data="fb_abort")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def feedback_list_keyboard(
    *,
    kind: FeedbackKind,
    items: list[tuple[UUID, FeedbackStatus, str]],
    offset: int,
    total: int,
) -> InlineKeyboardMarkup:
    page = items[:FEEDBACK_PAGE_SIZE]
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=feedback_list_label(status, body),
                callback_data=f"fb_open:{ticket_id}",
            ),
        ]
        for ticket_id, status, body in page
    ]
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        prev = max(0, offset - FEEDBACK_PAGE_SIZE)
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"fb_list:{kind.value}:{prev}"))
    if offset + FEEDBACK_PAGE_SIZE < total:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"fb_list:{kind.value}:{offset + FEEDBACK_PAGE_SIZE}",
            ),
        )
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=_BACK, callback_data=f"fb_menu:{kind.value}")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def feedback_detail_keyboard(kind: FeedbackKind) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К списку", callback_data=f"fb_list:{kind.value}:0")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def feedback_moderator_keyboard(ticket_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Решено", callback_data=f"fb_ok:{ticket_id}")],
            [InlineKeyboardButton(text="🟡 Взять в работу", callback_data=f"fb_work:{ticket_id}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"fb_no:{ticket_id}")],
        ],
    )


def feedback_author_notice_keyboard(ticket_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть", callback_data=f"fb_open:{ticket_id}")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def wellbeing_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📖 История самочувствия", callback_data="feel_hist:0")],
            [InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def wellbeing_saved_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏋️ Подстроить сегодняшнюю тренировку", callback_data="feel_adapt_today")],
            [InlineKeyboardButton(text="📅 Подстроить план недели", callback_data="feel_adapt_week")],
            [InlineKeyboardButton(text="📖 История самочувствия", callback_data="feel_hist:0")],
            [InlineKeyboardButton(text="Не надо, в меню", callback_data="home")],
        ],
    )


def wellbeing_history_keyboard(
    *,
    offset: int,
    has_more: bool,
    has_fresh_unapplied: bool = False,
    page_size: int = WELLBEING_HISTORY_PAGE_SIZE,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Новее", callback_data=f"feel_hist:{max(0, offset - page_size)}"))
    if has_more:
        nav.append(InlineKeyboardButton(text="Старее ➡️", callback_data=f"feel_hist:{offset + page_size}"))
    if nav:
        rows.append(nav)
    if has_fresh_unapplied:
        rows.append(
            [InlineKeyboardButton(text="🏋️ Подстроить сегодняшнюю тренировку", callback_data="feel_adapt_today")],
        )
        rows.append([InlineKeyboardButton(text="📅 Подстроить план недели", callback_data="feel_adapt_week")])
    rows.append([InlineKeyboardButton(text="✍️ Отметить самочувствие", callback_data="feel")])
    rows.append([InlineKeyboardButton(text="📜 К истории", callback_data="hist")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def wellbeing_missing_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Отметить самочувствие", callback_data="feel")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def wellbeing_rest_day_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Подстроить план недели", callback_data="feel_adapt_week")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def library_home_keyboard(items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """items: (program_id, button_label)."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=label, callback_data=f"lib_card:{program_id}")] for program_id, label in items
    ]
    rows.append([InlineKeyboardButton(text="🔗 Ввести код или ссылку", callback_data="code_link")])
    rows.append([InlineKeyboardButton(text="➕ Создать через AI", callback_data="prog_setup")])
    rows.append([how_it_works_button("library")])
    rows.append([InlineKeyboardButton(text=_TO_PROFILE, callback_data="profile")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def library_card_keyboard(
    *,
    program_id: str,
    status: str,
    is_author_template: bool,
    days: list[tuple[int, str]] | None = None,
    share_url: str | None = None,
) -> InlineKeyboardMarkup:
    """days: (day_position, button_label)."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=f"📅 {label}"[:64], callback_data=f"lib_day:{program_id}:{position}")]
        for position, label in days or []
    ]
    rows.append(
        [InlineKeyboardButton(text="▶️ Сделать активной как есть", callback_data=f"lib_apply:{program_id}:as_is")],
    )
    rows.append([InlineKeyboardButton(text="✨ Применить с адаптацией", callback_data=f"lib_apply:{program_id}:adapt")])
    rows.append([InlineKeyboardButton(text="✏️ Изменить текстом или голосом", callback_data=f"lib_edit:{program_id}")])
    rows.append([InlineKeyboardButton(text="🏷 Переименовать", callback_data=f"lib_rename:{program_id}")])
    if status == "draft" and is_author_template:
        rows.append(
            [InlineKeyboardButton(text="📤 Опубликовать и получить код", callback_data=f"lib_pub:{program_id}")],
        )
    if status == "published":
        if share_url:
            rows.append([InlineKeyboardButton(text="📤 Отправить код другу", url=share_url)])
        rows.append([InlineKeyboardButton(text="Снять с публикации", callback_data=f"lib_unpub:{program_id}")])
    rows.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"lib_del:{program_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ К библиотеке", callback_data="library")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def library_delete_confirm_keyboard(*, program_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"lib_del_ok:{program_id}")],
            [InlineKeyboardButton(text="⬅️ Нет, к карточке", callback_data=f"lib_card:{program_id}")],
        ],
    )


def library_day_keyboard(
    *,
    program_id: str,
    day_position: int,
    slots: list[tuple[int, str]] | None = None,
) -> InlineKeyboardMarkup:
    """slots: (slot_position, exercise_label)."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=slot_nav_button_text(position=position, label=label),
                callback_data=f"lib_slot:{program_id}:{day_position}:{position}",
            ),
        ]
        for position, label in slots or []
    ]
    rows.append([InlineKeyboardButton(text="⬅️ К карточке", callback_data=f"lib_card:{program_id}")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def library_slot_keyboard(
    *,
    program_id: str,
    day_position: int,
    slot_position: int,
    has_catalog_guide: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_catalog_guide:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📖 Как делать",
                    callback_data=f"lib_how:{program_id}:{day_position}:{slot_position}",
                ),
            ],
        )
    rows.append([InlineKeyboardButton(text="⬅️ К дню", callback_data=f"lib_day:{program_id}:{day_position}")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def library_edit_proposal_keyboard(*, program_id: str, can_approve: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_approve:
        rows.append([InlineKeyboardButton(text="💾 Сохранить в карточку", callback_data=f"lib_edit_ok:{program_id}")])
    rows.append([InlineKeyboardButton(text="✏️ Изменить ещё", callback_data=f"lib_edit:{program_id}")])
    rows.append([InlineKeyboardButton(text="❌ Отменить правку", callback_data=f"lib_edit_cancel:{program_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def library_title_keyboard(*, program_id: str, has_draft: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="✅ Оставить это название", callback_data=f"lib_title_keep:{program_id}")],
        [InlineKeyboardButton(text="📚 Библиотека", callback_data="library")],
    ]
    if has_draft:
        rows.append([InlineKeyboardButton(text="📝 К черновику", callback_data="prog_draft")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
