from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.enums import (
    SESSION_MINUTES_CHOICES,
    ActivityLevel,
    ExpectedInput,
    ExperienceLevel,
    Goal,
    ProfileField,
    Sex,
    Supplement,
    TrainingPlace,
)
from fitness_bot.domain.errors import InvalidProfileValue

_TIMEZONE_RE = re.compile(r"^[+-](?:0[0-9]|1[0-4]):[0-5][0-9]$")

PROFILE_FIELD_ORDER: tuple[ProfileField, ...] = (
    ProfileField.SEX,
    ProfileField.BIRTH_YEAR,
    ProfileField.HEIGHT,
    ProfileField.WEIGHT,
    ProfileField.EXPERIENCE,
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
)

# Edit-only / optional fields — not part of onboarding completeness.
# (experience_details, pharma, timezone)


def parse_timezone_offset(value: str) -> timedelta:
    if not _TIMEZONE_RE.match(value):
        raise InvalidProfileValue("timezone_offset must look like +03:00 or -05:00")
    sign = 1 if value[0] == "+" else -1
    hours, minutes = (int(part) for part in value[1:].split(":"))
    return timedelta(hours=sign * hours, minutes=sign * minutes)


def local_calendar_date(*, now: datetime, timezone_offset: str | None) -> date:
    utc_now = now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)
    if timezone_offset is None:
        return utc_now.date()
    offset = parse_timezone_offset(timezone_offset)
    return (utc_now + offset).date()


def local_day_bounds(*, now: datetime, timezone_offset: str | None) -> tuple[datetime, datetime]:
    """UTC half-open interval [start, end) for the local calendar day containing ``now``."""
    day = local_calendar_date(now=now, timezone_offset=timezone_offset)
    offset = parse_timezone_offset(timezone_offset) if timezone_offset is not None else timedelta(0)
    start_local = datetime.combine(day, time.min, tzinfo=timezone(offset))
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


class User(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    telegram_user_id: int
    chat_id: int
    display_name: str | None = None
    telegram_username: str | None = None
    is_moderator: bool = False
    sex: Sex | None = None
    birth_year: int | None = None
    height_cm: Decimal | None = None
    experience: ExperienceLevel | None = None
    experience_details: str | None = None
    days_per_week: int | None = None
    training_weekdays: frozenset[int] = Field(default_factory=frozenset)
    equipment: str | None = None
    training_place: TrainingPlace | None = None
    limitations: str | None = None
    activity_level: ActivityLevel | None = None
    session_minutes: int | None = None
    body_fat_pct: Decimal | None = None
    body_fat_set: bool = False
    supplements: frozenset[str] | None = None
    supplements_other: str | None = None
    diet_prefs: str | None = None
    nutrition_constraints: str | None = None
    pharma: str | None = None
    timezone_offset: str | None = None
    goal: Goal | None = None
    nutrition_stale: bool = False
    expected_input: ExpectedInput = ExpectedInput.NONE
    expected_field: str | None = None
    focus_slot: int | None = None
    active_program_id: UUID | None = None
    active_session_id: UUID | None = None
    pending_proposal_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def age(self, *, now: datetime | None = None) -> int | None:
        if self.birth_year is None:
            return None
        moment = now or datetime.now(UTC)
        year = local_calendar_date(now=moment, timezone_offset=self.timezone_offset).year
        return year - self.birth_year

    def is_profile_complete(self, *, has_weight: bool) -> bool:
        return self.next_missing_field(has_weight=has_weight) is None and self.goal is not None

    def next_missing_field(self, *, has_weight: bool) -> ProfileField | None:
        for field in PROFILE_FIELD_ORDER:
            if field == ProfileField.SEX and self.sex is None:
                return field
            if field == ProfileField.BIRTH_YEAR and self.birth_year is None:
                return field
            if field == ProfileField.HEIGHT and self.height_cm is None:
                return field
            if field == ProfileField.WEIGHT and not has_weight:
                return field
            if field == ProfileField.EXPERIENCE and self.experience is None:
                return field
            if field == ProfileField.DAYS_PER_WEEK and self.days_per_week is None:
                return field
            if field == ProfileField.TRAINING_WEEKDAYS:
                if self.days_per_week is None:
                    continue
                if len(self.training_weekdays) != self.days_per_week:
                    return field
            if field == ProfileField.EQUIPMENT and self.equipment is None:
                return field
            if field == ProfileField.TRAINING_PLACE and self.training_place is None:
                return field
            if field == ProfileField.LIMITATIONS and self.limitations is None:
                return field
            if field == ProfileField.ACTIVITY_LEVEL and self.activity_level is None:
                return field
            if field == ProfileField.SESSION_MINUTES and self.session_minutes is None:
                return field
            if field == ProfileField.BODY_FAT and not self.body_fat_set:
                return field
            if field == ProfileField.SUPPLEMENTS and self.supplements is None:
                return field
            if field == ProfileField.DIET_PREFS and self.diet_prefs is None:
                return field
            if field == ProfileField.NUTRITION_CONSTRAINTS and self.nutrition_constraints is None:
                return field
        return None

    def expect_input(
        self,
        expected_input: ExpectedInput,
        *,
        expected_field: str | None = None,
        focus_slot: int | None = None,
    ) -> None:
        self.expected_input = expected_input
        self.expected_field = expected_field
        self.focus_slot = focus_slot
        self.updated_at = datetime.now(UTC)

    def clear_expectation(self) -> None:
        self.expect_input(ExpectedInput.NONE)

    def sync_telegram_identity(self, *, display_name: str | None, telegram_username: str | None) -> None:
        name = display_name.strip() if display_name else None
        username = telegram_username.strip().lstrip("@") if telegram_username else None
        if name == "":
            name = None
        if username == "":
            username = None
        if self.display_name == name and self.telegram_username == username:
            return
        self.display_name = name
        self.telegram_username = username
        self.updated_at = datetime.now(UTC)

    def grant_moderator(self) -> None:
        self.is_moderator = True
        self.updated_at = datetime.now(UTC)

    def revoke_moderator(self) -> None:
        self.is_moderator = False
        self.updated_at = datetime.now(UTC)

    def public_label(self) -> str:
        if self.display_name:
            return self.display_name
        if self.telegram_username:
            return f"@{self.telegram_username}"
        return f"user_{str(self.id)[:8]}"

    def set_goal(self, goal: Goal) -> None:
        self.goal = goal
        self.nutrition_stale = True
        self.updated_at = datetime.now(UTC)

    def apply_profile_field(self, field: ProfileField, value: object, *, now: datetime | None = None) -> None:
        moment = now or datetime.now(UTC)
        if field == ProfileField.SEX:
            self.sex = Sex(str(value))
        elif field == ProfileField.BIRTH_YEAR:
            self.birth_year = self._validate_birth_year(int(str(value)), now=moment)
        elif field == ProfileField.HEIGHT:
            self.height_cm = self._validate_positive_decimal(value, name="height_cm")
        elif field == ProfileField.WEIGHT:
            raise InvalidProfileValue("weight is recorded via weight history, not profile columns")
        elif field == ProfileField.EXPERIENCE:
            try:
                self.experience = ExperienceLevel(str(value).strip())
            except ValueError as exc:
                raise InvalidProfileValue("experience must be beginner, intermediate, or advanced") from exc
        elif field == ProfileField.EXPERIENCE_DETAILS:
            text = str(value).strip()
            self.experience_details = text or None
        elif field == ProfileField.DAYS_PER_WEEK:
            days = int(str(value))
            if days < 1 or days > 7:
                raise InvalidProfileValue("days_per_week must be between 1 and 7")
            self.days_per_week = days
            self.training_weekdays = frozenset()
        elif field == ProfileField.TRAINING_WEEKDAYS:
            weekdays = self._validate_weekdays(value)
            if self.days_per_week is None:
                raise InvalidProfileValue("days_per_week must be set before training weekdays")
            if len(weekdays) != self.days_per_week:
                raise InvalidProfileValue("training weekdays count must equal days_per_week")
            self.training_weekdays = weekdays
        elif field == ProfileField.EQUIPMENT:
            text = str(value).strip()
            if not text:
                raise InvalidProfileValue("equipment must not be empty")
            self.equipment = text
        elif field == ProfileField.TRAINING_PLACE:
            try:
                self.training_place = TrainingPlace(str(value).strip())
            except ValueError as exc:
                raise InvalidProfileValue("training_place must be gym, home, outdoor, or mixed") from exc
        elif field == ProfileField.LIMITATIONS:
            self.limitations = str(value).strip()
        elif field == ProfileField.ACTIVITY_LEVEL:
            try:
                self.activity_level = ActivityLevel(str(value).strip())
            except ValueError as exc:
                raise InvalidProfileValue("activity_level must be sedentary, light, moderate, or high") from exc
        elif field == ProfileField.SESSION_MINUTES:
            minutes = int(str(value))
            if minutes not in SESSION_MINUTES_CHOICES:
                raise InvalidProfileValue("session_minutes must be one of 30, 45, 60, 90")
            self.session_minutes = minutes
        elif field == ProfileField.BODY_FAT:
            self._apply_body_fat(value)
        elif field == ProfileField.SUPPLEMENTS:
            self._apply_supplements(value)
        elif field == ProfileField.DIET_PREFS:
            self.diet_prefs = str(value).strip()
        elif field == ProfileField.NUTRITION_CONSTRAINTS:
            self.nutrition_constraints = str(value).strip()
        elif field == ProfileField.PHARMA:
            self.pharma = str(value).strip()
        elif field == ProfileField.TIMEZONE:
            offset = str(value).strip()
            parse_timezone_offset(offset)
            self.timezone_offset = offset
        else:
            raise InvalidProfileValue(f"unknown profile field: {field}")
        if field in {
            ProfileField.ACTIVITY_LEVEL,
            ProfileField.BODY_FAT,
            ProfileField.SUPPLEMENTS,
            ProfileField.DIET_PREFS,
            ProfileField.NUTRITION_CONSTRAINTS,
            ProfileField.PHARMA,
        }:
            self.nutrition_stale = True
        self.updated_at = datetime.now(UTC)

    def _apply_body_fat(self, value: object) -> None:
        raw = str(value).strip().casefold()
        if raw in {"unknown", "не знаю", "ne znayu", ""}:
            self.body_fat_pct = None
            self.body_fat_set = True
            return
        pct = self._validate_positive_decimal(value, name="body_fat_pct")
        if pct >= 100:
            raise InvalidProfileValue("body_fat_pct must be below 100")
        self.body_fat_pct = pct
        self.body_fat_set = True

    def _apply_supplements(self, value: object) -> None:
        codes = self._parse_supplement_codes(value)
        if Supplement.NONE.value in codes and len(codes) > 1:
            raise InvalidProfileValue("supplements 'none' cannot be combined with others")
        if not codes:
            raise InvalidProfileValue("supplements must not be empty")
        other_text: str | None = None
        if isinstance(value, dict):
            other_raw = value.get("other")
            if other_raw is not None:
                other_text = str(other_raw).strip() or None
        if Supplement.OTHER.value in codes:
            self.supplements_other = other_text
        else:
            self.supplements_other = None
        self.supplements = frozenset(codes)

    @staticmethod
    def _parse_supplement_codes(value: object) -> set[str]:
        allowed = {item.value for item in Supplement}
        if isinstance(value, dict):
            raw_items = value.get("codes", value.get("items", []))
        else:
            raw_items = value
        if isinstance(raw_items, str):
            text = raw_items.strip()
            if text.startswith("["):
                try:
                    raw_items = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise InvalidProfileValue("supplements must be a list of codes") from exc
            else:
                raw_items = [part.strip() for part in text.split(",") if part.strip()]
        if not isinstance(raw_items, list | tuple | set | frozenset):
            raise InvalidProfileValue("supplements must be a collection of codes")
        codes = {str(item).strip() for item in raw_items}
        if not codes or any(code not in allowed for code in codes):
            raise InvalidProfileValue("supplements contains unknown code")
        return codes

    def _validate_birth_year(self, year: int, *, now: datetime) -> int:
        if year <= 0:
            raise InvalidProfileValue("birth_year must be a positive integer")
        current_year = local_calendar_date(now=now, timezone_offset=self.timezone_offset).year
        if year >= current_year:
            raise InvalidProfileValue("birth_year must be earlier than the current calendar year")
        return year

    @staticmethod
    def _validate_positive_decimal(value: object, *, name: str) -> Decimal:
        from decimal import InvalidOperation

        try:
            number = Decimal(str(value).strip().replace(",", "."))
        except (InvalidOperation, AttributeError) as exc:
            raise InvalidProfileValue(f"{name} must be a positive number") from exc
        if number <= 0:
            raise InvalidProfileValue(f"{name} must be positive")
        return number

    @staticmethod
    def _validate_weekdays(value: object) -> frozenset[int]:
        if not isinstance(value, set | frozenset | list | tuple):
            raise InvalidProfileValue("training_weekdays must be a collection of ISO weekdays")
        weekdays = frozenset(int(item) for item in value)
        if not weekdays:
            raise InvalidProfileValue("training_weekdays must not be empty")
        if any(day < 1 or day > 7 for day in weekdays):
            raise InvalidProfileValue("weekday must be between 1 and 7")
        return weekdays
