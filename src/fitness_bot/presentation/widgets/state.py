"""Compact JSON for widget chat_data."""

from __future__ import annotations

import json
from typing import Any

from fitness_bot.presentation.widgets.limits import ensure_widget_state

PHASE_ERROR = '{"err":"phase"}'


def pack_state(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    ensure_widget_state(text, what="chat_data")
    return text


def read_state(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def as_number(value: object) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return round(number, 2)
