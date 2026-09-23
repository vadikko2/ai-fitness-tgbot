from __future__ import annotations

import json
from pathlib import Path

import pytest

from fitness_bot.service.catalog.jsonl import ExerciseJsonlRecord, load_exercises_jsonl, write_exercises_jsonl
from fitness_bot.service.handlers.commands.enrich_exercise_catalog import EnrichExerciseCatalogCommandHandler
from fitness_bot.service.models.commands.enrich_exercise_catalog import EnrichExerciseCatalogCommand
from fitness_bot.service.ports.video_search import VideoSearchHit


class _FakeLM:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls = 0

    async def complete(self, *, system: str, user: str) -> str:
        self.calls += 1
        assert system
        assert "Жим" in user or "жим" in user.lower()
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
async def test_enrich_handler_rewrites_technique_and_videos(tmp_path: Path) -> None:
    path = tmp_path / "exercises.jsonl"
    write_exercises_jsonl(
        path,
        [
            ExerciseJsonlRecord(
                name="Жим гантелей лёжа",
                primary_muscles=["грудь"],
                secondary_muscles=["трицепс"],
                technique="Коротко.",
                videos=[],
            ),
        ],
    )
    payload = json.dumps(
        {
            "items": [
                {
                    "name": "Жим гантелей лёжа",
                    "technique": (
                        "Лягте на скамью, стопы в пол, лопатки сведены. "
                        "Гантели над грудью, локти ~45°. Опустите до уровня груди и выжмите. "
                        "Не выгибайте поясницу дугой; не ударяйте гантели сверху."
                    ),
                    "video_queries": ["жим гантелей лёжа техника"],
                },
            ],
        },
        ensure_ascii=False,
    )
    handler = EnrichExerciseCatalogCommandHandler(_FakeLM(payload), _FakeSearch("youtube"), _FakeSearch("rutube"))
    result = await handler.handle(EnrichExerciseCatalogCommand(exercises_jsonl_path=path, max_videos_per_platform=2))
    assert result.exercises_updated == 1
    record = next(iter(load_exercises_jsonl(path).values()))
    assert len(record.technique) > 40
    assert "лопатки" in record.technique
    assert any(v.platform == "youtube" for v in record.videos)
    assert any(v.platform == "rutube" for v in record.videos)
