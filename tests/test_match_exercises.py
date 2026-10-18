from __future__ import annotations

from uuid import uuid4

import pytest

from fitness_bot.domain.catalog.match import CatalogExerciseView, match_exercises
from fitness_bot.domain.catalog.normalize import normalize_exercise_name, tokenize
from fitness_bot.service.handlers.queries.match_exercises import MatchExercisesQueryHandler
from fitness_bot.service.models.queries.match_exercises import MatchExercisesQuery
from fitness_bot.service.ports.exercise_catalog import InMemoryExerciseCatalog, record


def test_normalize_exercise_name_collapses_case_and_spaces() -> None:
    assert normalize_exercise_name("  Жим   Штанги  ") == "жим штанги"


def test_tokenize_keeps_cyrillic_words() -> None:
    assert tokenize("Жим штанги лёжа!") == {"жим", "штанги", "лёжа"}


def test_match_scores_name_higher_than_muscles() -> None:
    bench = CatalogExerciseView(
        id=uuid4(),
        name="Жим штанги лёжа",
        primary_muscles=("грудь",),
        secondary_muscles=("трицепс",),
    )
    curl = CatalogExerciseView(
        id=uuid4(),
        name="Подъём штанги на бицепс",
        primary_muscles=("бицепс",),
        secondary_muscles=(),
    )
    ranked = match_exercises(query="жим штанги", muscle=None, exercises=[curl, bench])
    assert [item.name for item in ranked] == ["Жим штанги лёжа", "Подъём штанги на бицепс"]
    assert ranked[0].score > ranked[1].score


def test_match_filters_by_muscle_then_falls_back() -> None:
    bench = CatalogExerciseView(
        id=uuid4(),
        name="Жим штанги лёжа",
        primary_muscles=("грудь",),
        secondary_muscles=("трицепс",),
    )
    squat = CatalogExerciseView(
        id=uuid4(),
        name="Приседания со штангой",
        primary_muscles=("квадрицепс",),
        secondary_muscles=("ягодицы",),
    )
    filtered = match_exercises(query="штанги жим", muscle="грудь", exercises=[bench, squat])
    assert [item.name for item in filtered] == ["Жим штанги лёжа"]

    fallback = match_exercises(query="приседания", muscle="бицепс", exercises=[bench, squat])
    assert [item.name for item in fallback] == ["Приседания со штангой"]


def test_match_returns_at_most_five_nonzero() -> None:
    exercises = [
        CatalogExerciseView(
            id=uuid4(),
            name=f"Жим вариант {index}",
            primary_muscles=("грудь",),
            secondary_muscles=(),
        )
        for index in range(8)
    ]
    ranked = match_exercises(query="жим", muscle=None, exercises=exercises)
    assert len(ranked) == 5
    assert all(item.score > 0 for item in ranked)


@pytest.mark.asyncio
async def test_match_exercises_query_handler() -> None:
    catalog = InMemoryExerciseCatalog(
        exercises=[
            record(
                exercise_id=uuid4(),
                name="Подтягивания",
                primary_muscles=["широчайшие"],
                secondary_muscles=["бицепс"],
            ),
            record(
                exercise_id=uuid4(),
                name="Тяга верхнего блока",
                primary_muscles=["широчайшие"],
                secondary_muscles=["бицепс"],
            ),
            record(
                exercise_id=uuid4(),
                name="Разгибание ног",
                primary_muscles=["квадрицепс"],
            ),
        ],
    )
    handler = MatchExercisesQueryHandler(catalog)
    result = await handler.handle(MatchExercisesQuery(query="подтягивания спина", muscle="широчайшие"))
    assert result.items
    assert result.items[0].name == "Подтягивания"
    assert result.items[0].score > 0


@pytest.mark.asyncio
async def test_get_exercise_guide_returns_technique_and_videos() -> None:
    from fitness_bot.service.handlers.queries.match_exercises import GetExerciseGuideQueryHandler
    from fitness_bot.service.models.queries.match_exercises import GetExerciseGuideQuery
    from fitness_bot.service.ports.exercise_catalog import guide
    from fitness_bot.service.ports.video_search import CatalogVideoLink

    exercise_id = uuid4()
    catalog = InMemoryExerciseCatalog(
        exercises=[record(exercise_id=exercise_id, name="Жим лёжа", primary_muscles=["грудь"])],
        guides={
            exercise_id: guide(
                exercise_id=exercise_id,
                name="Жим лёжа",
                technique="Лягте на скамью и выжмите гриф.",
                videos=[
                    CatalogVideoLink(
                        platform="rutube",
                        url="https://rutube.ru/video/demo/",
                        title="Техника жима",
                    ),
                ],
            ),
        },
    )
    handler = GetExerciseGuideQueryHandler(catalog)
    result = await handler.handle(GetExerciseGuideQuery(exercise_id=exercise_id))
    assert result.found is True
    assert result.name == "Жим лёжа"
    assert "скамью" in result.technique
    assert result.primary_muscles == ["грудь"]
    assert result.secondary_muscles == []
    assert result.videos[0].url == "https://rutube.ru/video/demo/"
