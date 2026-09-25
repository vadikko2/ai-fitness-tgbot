from __future__ import annotations

from collections.abc import Sequence

from fitness_bot.domain.enums import ExercisePlace, TrainingPlace

ALLOWED_EXERCISE_PLACES: frozenset[str] = frozenset(place.value for place in ExercisePlace)


def normalize_exercise_places(raw: Sequence[str] | None) -> tuple[str, ...]:
    """Parse and validate place tags; default to gym-only when missing."""
    if not raw:
        return (ExercisePlace.GYM.value,)
    places: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = str(item).strip().casefold()
        if value == TrainingPlace.MIXED.value:
            continue
        if value not in ALLOWED_EXERCISE_PLACES or value in seen:
            continue
        seen.add(value)
        places.append(value)
    if not places:
        return (ExercisePlace.GYM.value,)
    order = (ExercisePlace.GYM.value, ExercisePlace.HOME.value, ExercisePlace.OUTDOOR.value)
    return tuple(sorted(places, key=order.index))


def exercise_matches_training_place(
    places: Sequence[str],
    training_place: TrainingPlace | str | None,
) -> bool:
    """Whether an exercise may be prescribed for the user's training place."""
    if training_place is None:
        return True
    place = TrainingPlace(training_place) if isinstance(training_place, str) else training_place
    if place is TrainingPlace.MIXED:
        # Prefer portable / multi-place work; still allow single-place gym if tagged.
        return True
    normalized = set(normalize_exercise_places(places))
    return place.value in normalized
