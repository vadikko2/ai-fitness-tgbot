from __future__ import annotations

from datetime import UTC, datetime, timedelta

_COOLDOWN = timedelta(minutes=10)
_LAST_REFRESH_AT: dict[int, datetime] = {}


def check_nutrition_refresh_cooldown(
    telegram_user_id: int,
    *,
    now: datetime | None = None,
) -> timedelta | None:
    """Return remaining wait time if refresh is too soon; otherwise None."""
    moment = now or datetime.now(UTC)
    last = _LAST_REFRESH_AT.get(telegram_user_id)
    if last is None:
        return None
    elapsed = moment - last
    if elapsed >= _COOLDOWN:
        return None
    return _COOLDOWN - elapsed


def mark_nutrition_refresh(telegram_user_id: int, *, now: datetime | None = None) -> None:
    _LAST_REFRESH_AT[telegram_user_id] = now or datetime.now(UTC)


def clear_nutrition_refresh_cooldown(telegram_user_id: int | None = None) -> None:
    """Test helper: clear one user or the whole map."""
    if telegram_user_id is None:
        _LAST_REFRESH_AT.clear()
        return
    _LAST_REFRESH_AT.pop(telegram_user_id, None)


def format_cooldown_minutes(remaining: timedelta) -> int:
    seconds = max(0, int(remaining.total_seconds()))
    minutes = (seconds + 59) // 60
    return max(1, minutes)
