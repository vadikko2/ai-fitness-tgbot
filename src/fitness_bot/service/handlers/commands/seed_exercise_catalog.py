from __future__ import annotations

import json
from typing import Any

import cqrs

from fitness_bot.service.catalog.jsonl import (
    ExerciseJsonlRecord,
    load_exercises_jsonl,
    read_muscle_groups,
    upsert_exercise,
    write_exercises_jsonl,
)
from fitness_bot.service.catalog.llm_parse import dedupe_videos, extract_json_array, filter_relevant_video_hits
from fitness_bot.service.models.commands.seed_exercise_catalog import (
    SeedExerciseCatalogCommand,
    SeedExerciseCatalogResult,
)
from fitness_bot.service.ports.language_model import LanguageModel
from fitness_bot.service.ports.video_search import RutubeSearch, VideoSearchHit, YouTubeSearch
from fitness_bot.service.prompts import load_system_prompt, render_prompt


def _parse_author_items(raw_items: list[Any]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("catalog item must be an object")
        name = str(item.get("name") or "").strip()
        technique = str(item.get("technique") or "").strip()
        if not name:
            raise ValueError("catalog item missing name")
        if len(technique) > 500:
            technique = technique[:500]
        video_queries = [str(q).strip() for q in (item.get("video_queries") or []) if str(q).strip()]
        parsed.append(
            {
                "name": name,
                "primary_muscles": [str(m).strip() for m in (item.get("primary_muscles") or []) if str(m).strip()],
                "secondary_muscles": [str(m).strip() for m in (item.get("secondary_muscles") or []) if str(m).strip()],
                "technique": technique,
                "video_queries": video_queries,
            },
        )
    return parsed


class SeedExerciseCatalogCommandHandler(
    cqrs.RequestHandler[SeedExerciseCatalogCommand, SeedExerciseCatalogResult],
):
    def __init__(
        self,
        language_model: LanguageModel,
        youtube_search: YouTubeSearch,
        rutube_search: RutubeSearch,
    ) -> None:
        self._language_model = language_model
        self._youtube_search = youtube_search
        self._rutube_search = rutube_search
        self._events: list[cqrs.Event] = []

    @property
    def events(self) -> list[cqrs.Event]:
        return list(self._events)

    async def handle(self, request: SeedExerciseCatalogCommand) -> SeedExerciseCatalogResult:
        groups = read_muscle_groups(request.muscle_groups_path)
        store = load_exercises_jsonl(request.exercises_jsonl_path)
        system = load_system_prompt()
        per_platform = request.max_videos_per_platform

        for muscle_group in groups:
            existing_names = sorted({record.name for record in store.values()})
            user_prompt = render_prompt(
                "catalog_author.md",
                muscle_group=muscle_group,
                existing_names_json=json.dumps(existing_names, ensure_ascii=False),
            )
            raw = await self._language_model.complete(system=system, user=user_prompt)
            items = _parse_author_items(extract_json_array(raw))

            for item in items:
                hits: list[VideoSearchHit] = []
                for query in item["video_queries"]:
                    yt = await self._youtube_search.search(query, limit=per_platform)
                    rt = await self._rutube_search.search(query, limit=per_platform)
                    hits.extend(yt)
                    hits.extend(rt)
                hits = filter_relevant_video_hits(hits, exercise_name=item["name"])
                videos = dedupe_videos(hits, limit_per_platform=per_platform)
                record = ExerciseJsonlRecord(
                    name=item["name"],
                    primary_muscles=item["primary_muscles"],
                    secondary_muscles=item["secondary_muscles"],
                    technique=item["technique"],
                    videos=videos,
                )
                upsert_exercise(store, record)

        write_exercises_jsonl(request.exercises_jsonl_path, store.values())
        return SeedExerciseCatalogResult(
            muscle_groups=len(groups),
            exercises_written=len(store),
            path=str(request.exercises_jsonl_path),
        )
