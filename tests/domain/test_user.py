from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fitness_bot.domain.enums import ActivityLevel, ExperienceLevel, Goal, ProfileField, Sex
from fitness_bot.domain.errors import InvalidProfileValue
from fitness_bot.domain.users.user import User, local_calendar_date, local_day_bounds


def test_age_uses_utc_year_when_timezone_missing() -> None:
    user = User(telegram_user_id=1, chat_id=1, birth_year=1990)
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    assert user.age(now=now) == 36


def test_local_day_bounds_uses_timezone_offset() -> None:
    now = datetime(2026, 9, 21, 22, 30, tzinfo=UTC)  # 01:30 next day at +03:00
    start, end = local_day_bounds(now=now, timezone_offset="+03:00")
    assert start == datetime(2026, 9, 21, 21, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 22, 21, 0, tzinfo=UTC)
    assert local_calendar_date(now=now, timezone_offset="+03:00").isoformat() == "2026-09-22"


def test_age_uses_local_year_with_offset() -> None:
    user = User(telegram_user_id=1, chat_id=1, birth_year=1990, timezone_offset="+14:00")
    # 2025-12-31 22:00 UTC -> 2026-01-01 local
    now = datetime(2025, 12, 31, 22, 0, tzinfo=UTC)
    assert local_calendar_date(now=now, timezone_offset="+14:00").year == 2026
    assert user.age(now=now) == 36


def test_birth_year_must_be_before_current_year() -> None:
    user = User(telegram_user_id=1, chat_id=1)
    with pytest.raises(InvalidProfileValue):
        user.apply_profile_field(ProfileField.BIRTH_YEAR, 2026, now=datetime(2026, 1, 1, tzinfo=UTC))


def test_height_rejects_non_numeric_text() -> None:
    user = User(telegram_user_id=1, chat_id=1)
    with pytest.raises(InvalidProfileValue, match="positive number"):
        user.apply_profile_field(ProfileField.HEIGHT, "сто восемьдесят")


def test_training_weekdays_must_match_days_per_week() -> None:
    user = User(telegram_user_id=1, chat_id=1)
    user.apply_profile_field(ProfileField.DAYS_PER_WEEK, 3)
    with pytest.raises(InvalidProfileValue):
        user.apply_profile_field(ProfileField.TRAINING_WEEKDAYS, [1, 2])
    user.apply_profile_field(ProfileField.TRAINING_WEEKDAYS, [1, 2, 3])
    assert user.training_weekdays == frozenset({1, 2, 3})


def test_timezone_format() -> None:
    user = User(telegram_user_id=1, chat_id=1)
    user.apply_profile_field(ProfileField.TIMEZONE, "+03:00")
    assert user.timezone_offset == "+03:00"
    with pytest.raises(InvalidProfileValue):
        user.apply_profile_field(ProfileField.TIMEZONE, "UTC+3")


def test_profile_complete_requires_goal_and_weight() -> None:
    user = User(telegram_user_id=1, chat_id=1)
    user.sex = Sex.MALE
    user.birth_year = 1990
    user.height_cm = Decimal("180")
    user.experience = ExperienceLevel.BEGINNER
    user.days_per_week = 3
    user.training_weekdays = frozenset({1, 3, 5})
    user.equipment = "зал"
    user.limitations = ""
    user.activity_level = ActivityLevel.MODERATE
    user.session_minutes = 60
    user.body_fat_set = True
    user.supplements = frozenset({"none"})
    user.diet_prefs = ""
    assert user.next_missing_field(has_weight=False) == ProfileField.WEIGHT
    assert user.next_missing_field(has_weight=True) is None
    assert not user.is_profile_complete(has_weight=True)
    user.set_goal(Goal.FAT_LOSS)
    assert user.is_profile_complete(has_weight=True)
    assert user.nutrition_stale is True


def test_experience_must_be_enum() -> None:
    user = User(telegram_user_id=1, chat_id=1)
    user.apply_profile_field(ProfileField.EXPERIENCE, ExperienceLevel.INTERMEDIATE.value)
    assert user.experience == ExperienceLevel.INTERMEDIATE
    with pytest.raises(InvalidProfileValue):
        user.apply_profile_field(ProfileField.EXPERIENCE, "год в зале")


def test_body_fat_unknown_and_session_minutes() -> None:
    user = User(telegram_user_id=1, chat_id=1)
    user.apply_profile_field(ProfileField.BODY_FAT, "unknown")
    assert user.body_fat_set is True
    assert user.body_fat_pct is None
    user.apply_profile_field(ProfileField.BODY_FAT, "18.5")
    assert user.body_fat_pct == Decimal("18.5")
    user.apply_profile_field(ProfileField.SESSION_MINUTES, 45)
    assert user.session_minutes == 45
    with pytest.raises(InvalidProfileValue):
        user.apply_profile_field(ProfileField.SESSION_MINUTES, 20)


def test_supplements_none_exclusive_and_pharma_edit() -> None:
    user = User(telegram_user_id=1, chat_id=1)
    user.apply_profile_field(ProfileField.SUPPLEMENTS, ["protein", "creatine"])
    assert user.supplements == frozenset({"protein", "creatine"})
    with pytest.raises(InvalidProfileValue):
        user.apply_profile_field(ProfileField.SUPPLEMENTS, ["none", "protein"])
    user.apply_profile_field(ProfileField.SUPPLEMENTS, {"codes": ["other"], "other": "бета-аланин"})
    assert user.supplements_other == "бета-аланин"
    user.apply_profile_field(ProfileField.PHARMA, "")
    assert user.pharma == ""
    assert user.nutrition_stale is True
    assert ProfileField.PHARMA not in (
        __import__("fitness_bot.domain.users.user", fromlist=["PROFILE_FIELD_ORDER"]).PROFILE_FIELD_ORDER
    )
