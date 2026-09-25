from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fitness_bot.presentation.nutrition_refresh_cooldown import (
    check_nutrition_refresh_cooldown,
    clear_nutrition_refresh_cooldown,
    format_cooldown_minutes,
    mark_nutrition_refresh,
)


def test_nutrition_refresh_cooldown_blocks_within_10_minutes() -> None:
    clear_nutrition_refresh_cooldown()
    now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    assert check_nutrition_refresh_cooldown(101, now=now) is None
    mark_nutrition_refresh(101, now=now)
    remaining = check_nutrition_refresh_cooldown(101, now=now + timedelta(minutes=3))
    assert remaining is not None
    assert format_cooldown_minutes(remaining) == 7
    assert check_nutrition_refresh_cooldown(101, now=now + timedelta(minutes=10)) is None
    clear_nutrition_refresh_cooldown(101)
