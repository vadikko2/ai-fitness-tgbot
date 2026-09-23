from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fitness_bot.domain.errors import InvalidMeasurement

# Eight fixed circumference points from the plan.
FIXED_MEASUREMENT_SITES: tuple[tuple[str, str], ...] = (
    ("neck", "Шея"),
    ("chest", "Грудь"),
    ("waist", "Талия"),
    ("hips", "Бёдра/таз"),
    ("biceps", "Бицепс"),
    ("thigh", "Бедро"),
    ("calf", "Голень"),
    ("shoulder_girdle", "Плечевой пояс"),
)

# Laconic how-to texts for first open / offline seed (≤500 chars each).
DEFAULT_MEASUREMENT_GUIDES: dict[str, str] = {
    "neck": ("Встань ровно, смотри вперёд. Ленту оберни вокруг шеи чуть выше ключиц, параллельно полу, без давления."),
    "chest": (
        "Встань ровно, руки слегка в стороны или за головой. Ленту проведи под "
        "мышками через соски (или наиболее выступающую точку груди) — только "
        "торс, без рук, горизонтально. Выдох."
    ),
    "waist": (
        "Встань ровно, живот расслаблен. Измерь самый узкий участок торса "
        "(обычно чуть выше пупка), лента горизонтально."
    ),
    "hips": ("Ноги вместе. Ленту оберни по наиболее широкой части бёдер/ягодиц, параллельно полу."),
    "biceps": (
        "Рука расслаблена вдоль тела (или слегка согнута). Измерь самую толстую "
        "часть плеча, лента перпендикулярна кости."
    ),
    "thigh": ("Вес на обеих ногах. Измерь верхнюю треть бедра (самую толстую часть), лента горизонтально."),
    "calf": ("Встань ровно. Измерь самую толстую часть голени, лента горизонтально, без давления."),
    "shoulder_girdle": (
        "Руки вдоль тела. Ленту проведи через самые широкие точки плеч (дельты), спереди и сзади горизонтально."
    ),
}


def default_guide_for(code: str, name: str) -> str:
    text = DEFAULT_MEASUREMENT_GUIDES.get(code)
    if text is not None:
        return text
    return f"Встань ровно, расслабь мышцы. Ленту приложи к точке «{name}», держи горизонтально, без давления на кожу."


class MeasurementSite(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    code: str
    name: str
    is_custom: bool
    user_id: UUID | None = None

    @classmethod
    def fixed(cls, code: str, name: str) -> MeasurementSite:
        return cls(code=code, name=name, is_custom=False, user_id=None)

    @classmethod
    def custom(cls, *, user_id: UUID, name: str) -> MeasurementSite:
        cleaned = name.strip()
        if not cleaned:
            raise InvalidMeasurement("custom site name must not be empty")
        code = f"custom:{cleaned.casefold()}"
        return cls(code=code, name=cleaned, is_custom=True, user_id=user_id)


class MeasurementGuide(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    site_id: UUID
    instruction: str

    @field_validator("instruction")
    @classmethod
    def _validate_instruction(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise InvalidMeasurement("instruction must not be empty")
        if len(text) > 500:
            raise InvalidMeasurement("instruction must be at most 500 characters")
        return text


class MeasurementEntry(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    site_id: UUID
    centimeters: Decimal
    measured_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        site_id: UUID,
        centimeters: Decimal | str | float,
        measured_at: datetime,
    ) -> MeasurementEntry:
        value = Decimal(str(centimeters))
        if value <= 0:
            raise InvalidMeasurement("centimeters must be positive")
        return cls(user_id=user_id, site_id=site_id, centimeters=value, measured_at=measured_at)
