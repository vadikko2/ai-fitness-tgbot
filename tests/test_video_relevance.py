from __future__ import annotations

from fitness_bot.service.catalog.llm_parse import filter_relevant_video_hits, video_title_conflicts
from fitness_bot.service.ports.video_search import VideoSearchHit


def test_french_press_video_conflicts_with_leg_press() -> None:
    assert video_title_conflicts(
        "Жим одной ногой",
        "Французский жим с гантелью одной рукой: техника и нюансы",
    )
    assert not video_title_conflicts(
        "Жим одной ногой",
        "Жим одной ногой в тренажёре: техника и нюансы",
    )


def test_filter_drops_french_press_for_leg_press() -> None:
    hits = [
        VideoSearchHit(
            platform="rutube",
            url="https://rutube.ru/video/leg/",
            title="Жим одной ногой в тренажёре: техника и нюансы",
        ),
        VideoSearchHit(
            platform="rutube",
            url="https://rutube.ru/video/french/",
            title="Французский жим с гантелью одной рукой: техника и нюансы",
        ),
    ]
    filtered = filter_relevant_video_hits(hits, exercise_name="Жим одной ногой")
    assert [hit.url for hit in filtered] == ["https://rutube.ru/video/leg/"]


def test_filter_does_not_fallback_to_irrelevant_hits() -> None:
    hits = [
        VideoSearchHit(
            platform="rutube",
            url="https://rutube.ru/video/french/",
            title="Французский жим с гантелью одной рукой: техника и нюансы",
        ),
    ]
    assert filter_relevant_video_hits(hits, exercise_name="Жим одной ногой") == []


def test_stretch_title_with_zajimy_is_not_a_press_conflict() -> None:
    assert not video_title_conflicts(
        "Растяжка: шея — ухо к плечу стоя",
        "Растяжка и расслабление спины, шеи и плеч | Снимаем зажимы и убираем дискомфорт",
    )
