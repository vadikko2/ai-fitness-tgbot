from __future__ import annotations

import json
from pathlib import Path

import pytest

from fitness_bot.service.catalog.jsonl import (
    ExerciseJsonlRecord,
    ExerciseVideoLine,
    load_exercises_jsonl,
    read_muscle_groups,
    upsert_exercise,
    write_exercises_jsonl,
)
from fitness_bot.service.handlers.commands.seed_exercise_catalog import SeedExerciseCatalogCommandHandler
from fitness_bot.service.models.commands.seed_exercise_catalog import SeedExerciseCatalogCommand
from fitness_bot.service.ports.video_search import VideoSearchHit
from fitness_bot.shared.paths import EXERCISES_JSONL_PATH, MUSCLE_GROUPS_PATH


def test_committed_muscle_groups_and_jsonl_exist() -> None:
    groups = read_muscle_groups(MUSCLE_GROUPS_PATH)
    assert "грудь" in groups
    assert "бицепс" in groups
    store = load_exercises_jsonl(EXERCISES_JSONL_PATH)
    assert len(store) >= 300
    assert all(record.name and record.technique and record.primary_muscles for record in store.values())
    assert all(
        video.platform in ("youtube", "rutube") and video.url for record in store.values() for video in record.videos
    )
    assert any(record.videos for record in store.values())


def test_jsonl_upsert_replaces_by_normalized_name(tmp_path: Path) -> None:
    path = tmp_path / "exercises.jsonl"
    store = {}
    first = ExerciseJsonlRecord(
        name="Жим штанги",
        primary_muscles=["грудь"],
        secondary_muscles=[],
        technique="old",
        videos=[ExerciseVideoLine(platform="youtube", url="https://www.youtube.com/watch?v=aaa", title="a")],
    )
    second = ExerciseJsonlRecord(
        name="жим  штанги",
        primary_muscles=["грудь"],
        secondary_muscles=["трицепс"],
        technique="new",
        videos=[ExerciseVideoLine(platform="rutube", url="https://rutube.ru/video/bbb/", title="b")],
    )
    upsert_exercise(store, first)
    upsert_exercise(store, second)
    write_exercises_jsonl(path, store.values())
    loaded = load_exercises_jsonl(path)
    assert len(loaded) == 1
    record = loaded["жим штанги"]
    assert record.technique == "new"
    assert record.videos[0].platform == "rutube"
    raw = json.loads(path.read_text(encoding="utf-8").strip())
    assert raw["name"] == "жим  штанги"


class _FakeLM:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls = 0

    async def complete(self, *, system: str, user: str) -> str:
        self.calls += 1
        assert "грудь" in user
        assert system
        return self.payload


class _FakeSearch:
    def __init__(self, platform: str) -> None:
        self.platform = platform

    async def search(self, query: str, *, limit: int = 5) -> list[VideoSearchHit]:
        return [
            VideoSearchHit(
                platform=self.platform,
                url=f"https://example.com/{self.platform}/{query}",
                title=f"{self.platform}:{query}",
            ),
        ][:limit]


@pytest.mark.asyncio
async def test_seed_handler_writes_jsonl_without_model_urls(tmp_path: Path) -> None:
    groups = tmp_path / "muscle_groups.txt"
    groups.write_text("грудь\n", encoding="utf-8")
    out = tmp_path / "exercises.jsonl"
    payload = json.dumps(
        [
            {
                "name": "Жим гантелей лёжа",
                "primary_muscles": ["грудь"],
                "secondary_muscles": ["трицепс"],
                "technique": "Лягте на скамью и выжмите гантели.",
                "video_queries": ["жим гантелей лёжа техника"],
                "videos": [{"platform": "youtube", "url": "https://invented.invalid/x", "title": "nope"}],
            },
        ],
        ensure_ascii=False,
    )
    handler = SeedExerciseCatalogCommandHandler(_FakeLM(payload), _FakeSearch("youtube"), _FakeSearch("rutube"))
    result = await handler.handle(
        SeedExerciseCatalogCommand(muscle_groups_path=groups, exercises_jsonl_path=out),
    )
    assert result.exercises_written == 1
    loaded = load_exercises_jsonl(out)
    record = next(iter(loaded.values()))
    assert record.name == "Жим гантелей лёжа"
    urls = {video.url for video in record.videos}
    assert "https://invented.invalid/x" not in urls
    assert any(url.startswith("https://example.com/youtube/") for url in urls)
    assert any(url.startswith("https://example.com/rutube/") for url in urls)
