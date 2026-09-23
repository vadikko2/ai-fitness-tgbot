"""Exercise slot labels for Telegram navigation buttons."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from fitness_bot.domain.workout.document import ExerciseSlot


def slot_button_label(slot: ExerciseSlot, names: Mapping[UUID, str]) -> str:
    if slot.exercise_id is not None:
        name = names.get(slot.exercise_id)
        if name:
            return name
    if slot.custom_request:
        return slot.custom_request
    return f"Упражнение {slot.position}"


def slot_nav_button_text(*, position: int, label: str) -> str:
    """Telegram inline button label: position + exercise name (≤64)."""
    return f"{position}. {label}"[:64]


def build_slot_nav_items(
    slots: Sequence[ExerciseSlot],
    *,
    names: Mapping[UUID, str],
) -> list[tuple[int, str]]:
    """(position, exercise_label) for navigation keyboards."""
    return [(slot.position, slot_button_label(slot, names)) for slot in slots]
