"""Resolve the next open program day for rest / already-done screens."""

from __future__ import annotations

from fitness_bot.presentation.keyboards import WEEKDAY_LABELS


def resolve_alternative(source: object) -> tuple[int, str] | None:
    """Return (weekday, label) for the nearest open day, if any."""
    weekday = getattr(source, "alternative_weekday", None)
    title = getattr(source, "alternative_title", None)
    if isinstance(weekday, int) and 1 <= weekday <= 7:
        return weekday, _label(weekday, title)

    planned = [int(day) for day in list(getattr(source, "planned_weekdays", []) or []) if _weekday(day)]
    completed = {int(day) for day in list(getattr(source, "completed_weekdays", []) or []) if _weekday(day)}
    open_days = [day for day in planned if day not in completed]
    if not open_days:
        return None
    today = getattr(source, "weekday", None)
    if isinstance(today, int):
        open_days.sort(key=lambda day: (day - today) % 7)
    else:
        open_days.sort()
    day = open_days[0]
    return day, _label(day, None)


def put_alternative(data: dict[str, object], source: object, *, again: bool = False) -> None:
    mode = str(data.get("mode") or "")
    if mode not in {"again", "rest"}:
        data.pop("alt", None)
        data.pop("altDay", None)
        data.pop("cta", None)
        return
    found = resolve_alternative(source)
    if found is None:
        data.pop("alt", None)
        data.pop("altDay", None)
        data.pop("cta", None)
        return
    weekday, label = found
    prefix = "Ещё одну: " if again or mode == "again" else ""
    data["altDay"] = weekday
    data["alt"] = f"{prefix}{label}"[:42]
    data["cta"] = label[:42]


def _weekday(value: object) -> bool:
    try:
        day = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return 1 <= day <= 7


def _label(weekday: int, title: object) -> str:
    day = WEEKDAY_LABELS.get(weekday, str(weekday))
    text = str(title or "").strip()
    if not text:
        return day
    return f"{day} · {text}"
