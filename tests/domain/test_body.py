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
