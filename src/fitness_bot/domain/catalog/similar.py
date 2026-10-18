from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from fitness_bot.domain.catalog.normalize import tokenize
from fitness_bot.domain.catalog.places import exercise_matches_training_place
from fitness_bot.domain.enums import TrainingPlace

# Name prefixes ("Растяжка: …") that mark a different kind of work, not an equivalent swap.
SPECIAL_CATEGORY_PREFIXES: tuple[str, ...] = (
    "растяжка",
    "лфк",
    "для пожилых",
    "мобилити",
    "беременность",
    "для детей",
    "кардио",
    "изометрия",
    "плиометрика",
)

# The catalog has no equipment field: these name stems stand in for it.
EQUIPMENT_STEMS: tuple[str, ...] = (
    "штанг",
    "гантел",
    "гир",
    "тренажер",
    "блок",
    "кроссовер",
    "смит",
    "резин",
    "лент",
    "trx",
    "петл",
    "турник",
    "перекладин",
    "брусь",
    "кольц",
    "медбол",
    "фитбол",
    "гравитрон",
)

_STOPWORDS = frozenset({"с", "на", "в", "и", "к", "от", "из", "под", "до", "по", "со", "для", "одной", "двумя"})


class SimilarityExercise(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def name(self) -> str: ...

    @property
    def primary_muscles(self) -> tuple[str, ...]: ...

    @property
    def secondary_muscles(self) -> tuple[str, ...]: ...

    @property
    def places(self) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class SimilarCandidate:
    exercise_id: UUID
    name: str
    score: int


@dataclass(frozen=True, slots=True)
class SimilarPage:
    items: list[SimilarCandidate]
    has_more: bool


def _fold(text: str) -> str:
    return text.casefold().replace("ё", "е")


def _category(name: str) -> str | None:
    head, sep, _ = _fold(name).partition(":")
    if not sep:
        return None
    head = head.strip()
    return head if head.startswith(SPECIAL_CATEGORY_PREFIXES) else None


def _name_tokens(name: str) -> tuple[set[str], set[str]]:
    """(movement tokens, equipment stems) of an exercise name."""
    tokens = {token for token in tokenize(_fold(name)) if token not in _STOPWORDS and len(token) > 2}
    equipment = {stem for stem in EQUIPMENT_STEMS if any(token.startswith(stem) for token in tokens)}
    movement = {token for token in tokens if not any(token.startswith(stem) for stem in EQUIPMENT_STEMS)}
    return movement, equipment


def _muscles(values: Sequence[str]) -> set[str]:
    return {_fold(value).strip() for value in values if value.strip()}


def similarity_score(target: SimilarityExercise, candidate: SimilarityExercise) -> int:
    """Muscle overlap first, then shared movement words; 0 means «not similar»."""
    target_primary, target_secondary = _muscles(target.primary_muscles), _muscles(target.secondary_muscles)
    cand_primary, cand_secondary = _muscles(candidate.primary_muscles), _muscles(candidate.secondary_muscles)
    primary_overlap = len(target_primary & cand_primary)
    if target_primary and primary_overlap == 0:
        return 0
    score = (
        3 * primary_overlap
        + len(target_secondary & cand_secondary)
        + len(target_primary & cand_secondary)
        + len(target_secondary & cand_primary)
        - len(cand_primary - target_primary - target_secondary)
    )
    target_movement, target_equipment = _name_tokens(target.name)
    cand_movement, cand_equipment = _name_tokens(candidate.name)
    score += 2 * min(len(target_movement & cand_movement), 2)
    score += 1 if target_equipment & cand_equipment else 0
    return max(score, 0)


def similar_exercises(
    target: SimilarityExercise,
    pool: Sequence[SimilarityExercise],
    *,
    training_place: TrainingPlace | str | None,
    exclude_ids: Collection[UUID] = (),
    offset: int = 0,
    limit: int = 3,
) -> SimilarPage:
    """Catalog alternatives for a workout slot: same place, overlapping muscles, same kind of work."""
    excluded = {target.id, *exclude_ids}
    category = _category(target.name)
    scored: list[SimilarCandidate] = []
    for candidate in pool:
        if candidate.id in excluded or _category(candidate.name) != category:
            continue
        if not exercise_matches_training_place(candidate.places, training_place):
            continue
        score = similarity_score(target, candidate)
        if score <= 0:
            continue
        scored.append(SimilarCandidate(exercise_id=candidate.id, name=candidate.name, score=score))
    scored.sort(key=lambda item: (-item.score, item.name.casefold()))
    start = max(0, offset)
    return SimilarPage(items=scored[start : start + limit], has_more=len(scored) > start + limit)
