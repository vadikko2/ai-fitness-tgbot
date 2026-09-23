from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from fitness_bot.domain.enums import ActivityLevel, ExperienceLevel, Goal, ProfileField, Sex, Supplement
from fitness_bot.domain.program_catalog import (
    PROGRAM_TYPE_COPY,
    PROGRAM_TYPE_FREQUENT,
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
    ProfileField.EQUIPMENT: "🏋️ Место и оборудование",
    ProfileField.LIMITATIONS: "⚠️ Ограничения",
    ProfileField.ACTIVITY_LEVEL: "🚶 Активность вне зала",
    ProfileField.SESSION_MINUTES: "⏱ Длительность тренировки",
    ProfileField.BODY_FAT: "🧪 % жира",
    ProfileField.SUPPLEMENTS: "💊 Спортпит",
    ProfileField.DIET_PREFS: "🥗 Пищевые предпочтения",
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
    ProfileField.LIMITATIONS,
    ProfileField.ACTIVITY_LEVEL,
    ProfileField.SESSION_MINUTES,
    ProfileField.BODY_FAT,
    ProfileField.SUPPLEMENTS,
    ProfileField.DIET_PREFS,
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
_BACK = "⬅️ Назад"
_CANCEL = "❌ Отмена"
_CONFIRM = "✅ Подтвердить"
_DONE = "✅ Готово"
_EDIT_TEXT = "✏️ Изменить текстом"


def home_keyboard(
    *,
    show_coach_badge: bool = False,
    active_clients_count: int = 0,
    is_moderator: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🏋️ Тренировка сегодня", callback_data="sess")],
        [InlineKeyboardButton(text="📋 Мой план сейчас", callback_data="prog")],
        [InlineKeyboardButton(text="📚 Библиотека программ", callback_data="library")],
        [InlineKeyboardButton(text="🔗 Ввести код или ссылку", callback_data="code_link")],
        [
            InlineKeyboardButton(text="⚖️ Вес", callback_data="wt_menu"),
            InlineKeyboardButton(text="📏 Обхваты", callback_data="meas_menu"),
        ],
        [InlineKeyboardButton(text="🥗 Питание", callback_data="nutr")],
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            InlineKeyboardButton(text="📜 История", callback_data="hist"),
        ],
        [InlineKeyboardButton(text="🔎 Найти тренера", callback_data="coach_search")],
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
        inline_keyboard=[[InlineKeyboardButton(text="👌 Без ограничений", callback_data=f"{prefix}:none")]],
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
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def weight_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Записать вес", callback_data="wt_log")],
            [InlineKeyboardButton(text="📈 История", callback_data="wt_hist")],
            [InlineKeyboardButton(text="⏰ Расписание напоминаний", callback_data="wt_remind")],
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
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    return InlineKeyboardMarkup(
        inline_keyboard=[
            frequent,
            splits,
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
) -> InlineKeyboardMarkup:
    """days: list of (day_position, button_label)."""
    rows: list[list[InlineKeyboardButton]] = []
    for position, label in days or []:
        rows.append(
            [InlineKeyboardButton(text=f"📅 {label}"[:64], callback_data=f"prog_day:{position}")],
        )
    rows.append([InlineKeyboardButton(text="✏️ Изменить текстом или голосом", callback_data="prog_edit")])
    if can_approve:
        rows.append([InlineKeyboardButton(text="✅ Сделать активной", callback_data="prog_ok")])
    rows.append([InlineKeyboardButton(text="❌ Отменить черновик", callback_data="draft_cancel")])
    rows.append([InlineKeyboardButton(text="📋 К программе", callback_data="prog")])
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
    rows.append([InlineKeyboardButton(text="✏️ Изменить программу", callback_data="prog_edit_menu")])
    if has_pending:
        rows.append([InlineKeyboardButton(text="📝 Есть черновик — открыть", callback_data="prog_draft")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    _ = has_active
    return InlineKeyboardMarkup(inline_keyboard=rows)


def program_edit_menu_keyboard(*, has_pending: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_pending:
        rows.append([InlineKeyboardButton(text="📝 Открыть черновик", callback_data="prog_draft")])
    rows.append([InlineKeyboardButton(text="🔄 Задать / сменить программу", callback_data="prog_setup")])
    rows.append([InlineKeyboardButton(text="📋 К программе", callback_data="prog")])
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


def session_template_keyboard(*, week_finished: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="▶️ Начать как в плане", callback_data="sess_plan")],
        [InlineKeyboardButton(text="✏️ Изменить тренировку", callback_data="sess_tmpl_edit")],
    ]
    new_week_label = "🆕 Начать новую тренировочную неделю"
    if week_finished:
        rows.insert(0, [InlineKeyboardButton(text=new_week_label, callback_data="sess_new_week")])
    else:
        rows.append([InlineKeyboardButton(text=new_week_label, callback_data="sess_new_week")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_template_edit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Написать что поменять", callback_data="sess_tmpl_edit_text")],
            [InlineKeyboardButton(text="✨ Перегенерировать по истории", callback_data="sess_gen")],
            [InlineKeyboardButton(text="⬅️ Назад к плану", callback_data="sess")],
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


def next_session_actions_keyboard(*, can_approve: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_approve:
        rows.append([InlineKeyboardButton(text=_CONFIRM, callback_data="sess_gen_ok")])
    rows.append([InlineKeyboardButton(text=_CANCEL, callback_data="draft_cancel")])
    rows.append([InlineKeyboardButton(text=_MENU, callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def nutrition_no_program_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Программа", callback_data="prog")],
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def session_card_keyboard(
    *,
    slots: list[tuple[int, str]] | None = None,
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
    rows.append([InlineKeyboardButton(text="✏️ Изменить", callback_data="sess_edit")])
    rows.append([InlineKeyboardButton(text="🏁 Выполнить всю тренировку", callback_data="sess_all")])
    rows.append([InlineKeyboardButton(text="🔄 Начать заново", callback_data="sess_restart")])
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
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="✅ Как в плане → дальше", callback_data=f"slot_plan:{position}")],
        [InlineKeyboardButton(text="✏️ Вес и повторы", callback_data=f"slot_fact:{position}")],
    ]
    if has_catalog_guide:
        rows.append([InlineKeyboardButton(text="📖 Как делать", callback_data=f"slot_how:{position}")])
    if has_actual:
        label = "🎥 Заменить своё видео" if has_technique_video else "🎥 Загрузить видео упражнения"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"slot_video:{position}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад к тренировке", callback_data="sess")])
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
            [InlineKeyboardButton(text=_MENU, callback_data="home")],
        ],
    )


def session_rest_keyboard(*, week_finished: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    new_week = [InlineKeyboardButton(text="🆕 Начать новую тренировочную неделю", callback_data="sess_new_week")]
    if week_finished:
        rows.append(new_week)
        rows.append([InlineKeyboardButton(text="📜 История", callback_data="hist")])
    else:
        rows.append([InlineKeyboardButton(text="📜 История", callback_data="hist")])
        rows.append(new_week)
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
