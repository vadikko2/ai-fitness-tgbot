from __future__ import annotations

from dataclasses import dataclass

from fitness_bot.domain.enums import ProgramStatus, ProgramType, TrainingStyle


@dataclass(frozen=True, slots=True)
class ProgramKindCopy:
    label: str
    blurb: str
    detail: str


PROGRAM_STATUS_LABELS: dict[ProgramStatus, str] = {
    ProgramStatus.DRAFT: "черновик",
    ProgramStatus.PUBLISHED: "опубликована",
    ProgramStatus.ACTIVE: "активна",
    ProgramStatus.ARCHIVED: "в архиве",
}


PROGRAM_TYPE_COPY: dict[ProgramType, ProgramKindCopy] = {
    ProgramType.FULL_BODY: ProgramKindCopy(
        label="🧍 Фуллбади",
        blurb="Каждую тренировку — всё тело. Удобно при 2–3 днях в неделю.",
        detail=(
            "В каждой сессии задействованы основные группы мышц. "
            "Подходит, если тренируешься 2–3 раза в неделю и хочешь равномерную нагрузку."
        ),
    ),
    ProgramType.UPPER_LOWER: ProgramKindCopy(
        label="↕️ Верх / Низ",
        blurb="День верха (грудь, спина, плечи, руки) чередуется с днём низа (ноги, ягодицы, кор).",
        detail=(
            "Классическое чередование верха и низа тела. "
            "Обычно 3–4 тренировки в неделю: хватает объёма и времени на восстановление."
        ),
    ),
    ProgramType.PUSH_PULL: ProgramKindCopy(
        label="🔀 Тяни-толкай",
        blurb="Дни по движению: жимы / тяги / (часто) ноги. Классика 3–6 дней.",
        detail=(
            "Дни делятся по паттерну движения: жимы, тяги, ноги. Гибко масштабируется от 3 до 6 тренировок в неделю."
        ),
    ),
    ProgramType.ANTAGONIST: ProgramKindCopy(
        label="⚖️ Антагонисты",
        blurb="В одной сессии пары противоположных мышц (грудь+спина, бицепс+трицепс).",
        detail=(
            "В одном дне сочетаются мышцы-антагонисты: грудь со спиной, бицепс с трицепсом. "
            "Удобно при 3–5 тренировках в неделю."
        ),
    ),
    ProgramType.SYNERGIST: ProgramKindCopy(
        label="🔗 Синергисты",
        blurb="Крупная группа + её помощник (грудь+трицепс, спина+бицепс).",
        detail=(
            "Основная мышца и её помощники в одной сессии: грудь с трицепсом, спина с бицепсом. "
            "Типично 3–5 дней в неделю."
        ),
    ),
    ProgramType.SPLIT: ProgramKindCopy(
        label="🧩 Бро-сплит",
        blurb="В день одна крупная группа, большой объём раз в неделю.",
        detail=("Каждый день — одна крупная группа мышц с большим объёмом. Рассчитано на 5–6 тренировок в неделю."),
    ),
}

TRAINING_STYLE_COPY: dict[TrainingStyle, ProgramKindCopy] = {
    TrainingStyle.CLASSIC: ProgramKindCopy(
        label="🏋️ Классика",
        blurb="Обычные подходы и отдых — баланс роста мышц и восстановления.",
        detail=(
            "Классическая схема: несколько подходов, умеренный отдых, RPE около 7–8. "
            "Универсальный вариант для гипертрофии и поддержания формы."
        ),
    ),
    TrainingStyle.STRENGTH: ProgramKindCopy(
        label="💪 Сила 5×5",
        blurb="Фокус на силу в базах: мало повторов, длинный отдых (в духе 5×5).",
        detail=(
            "Базовые движения с низкими повторами и длинным отдыхом. "
            "Подходит, когда цель — прибавить силу в приседе, жиме и тяге."
        ),
    ),
    TrainingStyle.CIRCUIT: ProgramKindCopy(
        label="🔄 Круговая",
        blurb="Упражнения цепочкой почти без паузы — выносливость и расход энергии.",
        detail=(
            "Упражнения идут одно за другим с коротким отдыхом. "
            "Больше кардионагрузки и расхода калорий при том же времени."
        ),
    ),
    TrainingStyle.HIT: ProgramKindCopy(
        label="⚡ HIT",
        blurb="Коротко и жёстко: 1–2 рабочих подхода до отказа, редкие тренировки.",
        detail=(
            "Мало рабочих подходов до высокого RPE или отказа. "
            "Сессии короче, но интенсивнее — важно не перетренироваться."
        ),
    ),
}

PROGRAM_TYPE_FREQUENT: tuple[ProgramType, ...] = (
    ProgramType.FULL_BODY,
    ProgramType.UPPER_LOWER,
    ProgramType.PUSH_PULL,
)
PROGRAM_TYPE_SPLITS: tuple[ProgramType, ...] = (
    ProgramType.ANTAGONIST,
    ProgramType.SYNERGIST,
    ProgramType.SPLIT,
)
TRAINING_STYLE_ORDER: tuple[TrainingStyle, ...] = (
    TrainingStyle.CLASSIC,
    TrainingStyle.STRENGTH,
    TrainingStyle.CIRCUIT,
    TrainingStyle.HIT,
)


def program_type_label(program_type: ProgramType | str) -> str:
    if isinstance(program_type, str):
        program_type = ProgramType(program_type)
    return PROGRAM_TYPE_COPY[program_type].label


def program_status_label(status: ProgramStatus | str) -> str:
    if isinstance(status, str):
        status = ProgramStatus(status)
    return PROGRAM_STATUS_LABELS[status]


def training_style_label(style: TrainingStyle | str) -> str:
    if isinstance(style, str):
        style = TrainingStyle(style)
    return TRAINING_STYLE_COPY[style].label


def structure_choice_items() -> list[ProgramKindCopy]:
    """Ordered catalog rows for the structure-of-week setup step."""
    return [PROGRAM_TYPE_COPY[program_type] for program_type in (*PROGRAM_TYPE_FREQUENT, *PROGRAM_TYPE_SPLITS)]


def planner_program_type_hint(program_type: ProgramType) -> str:
    return PROGRAM_TYPE_COPY[program_type].detail


def planner_training_styles_guide() -> str:
    """All training styles for per-day assignment in program generation."""
    return "\n".join(f"- {style.value}: {TRAINING_STYLE_COPY[style].detail}" for style in TRAINING_STYLE_ORDER)
