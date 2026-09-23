from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import Decimal
from uuid import uuid4

import pytest

from fitness_bot.domain.body.measurement import (
    DEFAULT_MEASUREMENT_GUIDES,
    FIXED_MEASUREMENT_SITES,
    MeasurementEntry,
    MeasurementSite,
    default_guide_for,
)
from fitness_bot.domain.body.reminder import WeightReminder
from fitness_bot.domain.body.weight import WeightEntry
from fitness_bot.domain.enums import WeightSource
from fitness_bot.domain.errors import InvalidMeasurement, InvalidReminder, InvalidWeight


def test_weight_must_be_positive() -> None:
    with pytest.raises(InvalidWeight):
        WeightEntry.create(
            user_id=uuid4(),
            kilograms=0,
            measured_at=datetime.now(UTC),
            source=WeightSource.MANUAL,
        )


def test_weight_rerecord_must_be_positive() -> None:
    entry = WeightEntry.create(
        user_id=uuid4(),
        kilograms="80",
        measured_at=datetime.now(UTC),
        source=WeightSource.MANUAL,
    )
    with pytest.raises(InvalidWeight):
        entry.rerecord(kilograms=0, measured_at=datetime.now(UTC), source=WeightSource.MANUAL)


def test_measurement_must_be_positive() -> None:
    with pytest.raises(InvalidMeasurement):
        MeasurementEntry.create(
            user_id=uuid4(),
            site_id=uuid4(),
            centimeters=Decimal("0"),
            measured_at=datetime.now(UTC),
        )


def test_custom_site_requires_name() -> None:
    with pytest.raises(InvalidMeasurement):
        MeasurementSite.custom(user_id=uuid4(), name="  ")


def test_default_measurement_guides_cover_fixed_sites() -> None:
    assert set(DEFAULT_MEASUREMENT_GUIDES) == {code for code, _ in FIXED_MEASUREMENT_SITES}
    for code, name in FIXED_MEASUREMENT_SITES:
        text = default_guide_for(code, name)
        assert 0 < len(text) <= 500
        assert "лент" in text.lower()


def test_reminder_weekdays_required() -> None:
    with pytest.raises(InvalidReminder):
        WeightReminder.create(user_id=uuid4(), local_time=time(8, 0), weekdays=[])


def test_default_weight_reminder_is_sunday_morning() -> None:
    reminder = WeightReminder.default_for_user(user_id=uuid4())
    assert reminder.weekdays == frozenset({7})
    assert reminder.local_time == time(9, 0)


def test_default_progress_photo_reminder_matches_weight() -> None:
    from fitness_bot.domain.body.reminder import ProgressPhotoReminder

    reminder = ProgressPhotoReminder.default_for_user(user_id=uuid4())
    assert reminder.weekdays == frozenset({7})
    assert reminder.local_time == time(9, 0)


def test_progress_photo_reminder_weekdays_required() -> None:
    from fitness_bot.domain.body.reminder import ProgressPhotoReminder

    with pytest.raises(InvalidReminder):
        ProgressPhotoReminder.create(user_id=uuid4(), local_time=time(8, 0), weekdays=[])


def test_progress_photo_object_key_path() -> None:
    from fitness_bot.domain.body.progress_photo import progress_photo_object_key
    from fitness_bot.domain.enums import ProgressPhotoAngle

    user_id = uuid4()
    set_id = uuid4()
    key = progress_photo_object_key(
        user_id=user_id,
        set_id=set_id,
        angle=ProgressPhotoAngle.SIDE,
    )
    assert key == f"users/{user_id}/progress_photos/{set_id}/side.jpg"


def test_progress_photo_set_completes_only_with_three_angles() -> None:
    from datetime import date

    from fitness_bot.domain.body.progress_photo import ProgressPhotoSet
    from fitness_bot.domain.enums import ProgressPhotoAngle

    photo_set = ProgressPhotoSet.create(user_id=uuid4(), local_date=date(2026, 9, 23))
    assert photo_set.next_angle() == ProgressPhotoAngle.FRONT
    photo_set.upsert_photo(angle=ProgressPhotoAngle.FRONT, content_type="image/jpeg", byte_size=100)
    assert not photo_set.complete
    assert photo_set.next_angle() == ProgressPhotoAngle.SIDE
    photo_set.upsert_photo(angle=ProgressPhotoAngle.SIDE, content_type="image/jpeg", byte_size=100)
    assert photo_set.next_angle() == ProgressPhotoAngle.BACK
    photo_set.upsert_photo(angle=ProgressPhotoAngle.BACK, content_type="image/jpeg", byte_size=100)
    assert photo_set.complete
    assert photo_set.next_angle() is None


def test_progress_photo_same_angle_replace_clears_file_id() -> None:
    from datetime import date

    from fitness_bot.domain.body.progress_photo import ProgressPhotoSet
    from fitness_bot.domain.enums import ProgressPhotoAngle

    photo_set = ProgressPhotoSet.create(user_id=uuid4(), local_date=date(2026, 9, 23))
    photo, _ = photo_set.upsert_photo(angle=ProgressPhotoAngle.FRONT, content_type="image/jpeg", byte_size=100)
    photo_set.remember_file_id(photo_id=photo.id, telegram_file_id="file-1")
    assert photo_set.photo_for(ProgressPhotoAngle.FRONT).telegram_file_id == "file-1"
    photo_set.upsert_photo(angle=ProgressPhotoAngle.FRONT, content_type="image/jpeg", byte_size=200)
    assert photo_set.photo_for(ProgressPhotoAngle.FRONT).telegram_file_id is None
    assert photo_set.photo_for(ProgressPhotoAngle.FRONT).byte_size == 200
