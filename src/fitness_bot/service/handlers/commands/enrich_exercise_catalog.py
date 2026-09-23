from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import cqrs
import httpx

from fitness_bot.service.catalog.jsonl import (
    ExerciseJsonlRecord,
    load_exercises_jsonl,
    upsert_exercise,
    write_exercises_jsonl,
)
from fitness_bot.service.catalog.llm_parse import dedupe_videos, extract_json_array, filter_relevant_video_hits
from fitness_bot.service.models.commands.enrich_exercise_catalog import (
    EnrichExerciseCatalogCommand,
    EnrichExerciseCatalogResult,
)
from fitness_bot.service.ports.language_model import LanguageModel
from fitness_bot.service.ports.video_search import RutubeSearch, VideoSearchHit, YouTubeSearch
from fitness_bot.service.prompts import load_system_prompt, render_prompt


def _parse_enrich_items(raw_items: list[Any], *, expected_names: set[str]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("enrich item must be an object")
        name = str(item.get("name") or "").strip()
        technique = str(item.get("technique") or "").strip()
        if not name or name not in expected_names:
            continue
        if not technique:
            continue
        if len(technique) > 500:
            technique = technique[:500]
        video_queries = [str(q).strip() for q in (item.get("video_queries") or []) if str(q).strip()]
        if not video_queries:
            video_queries = [f"{name} техника"]
        parsed.append({"name": name, "technique": technique, "video_queries": video_queries[:2]})
    return parsed


def _needs_enrichment(
    record: ExerciseJsonlRecord,
    *,
    only_short_technique: bool,
    short_technique_chars: int,
    only_missing_videos: bool,
) -> bool:
    short = len(record.technique.strip()) < short_technique_chars
    missing_videos = not record.videos
    if only_short_technique and only_missing_videos:
        return short or missing_videos
    if only_short_technique:
        return short
    if only_missing_videos:
        return missing_videos
    return True


class EnrichExerciseCatalogCommandHandler(
    cqrs.RequestHandler[EnrichExerciseCatalogCommand, EnrichExerciseCatalogResult],
):
    def __init__(
        self,
        language_model: LanguageModel,
        youtube_search: YouTubeSearch,
        rutube_search: RutubeSearch,
        *,
        search_concurrency: int = 6,
    ) -> None:
        self._language_model = language_model
        self._youtube_search = youtube_search
        self._rutube_search = rutube_search
        self._search_sema = asyncio.Semaphore(max(1, search_concurrency))
        self._events: list[cqrs.Event] = []

    @property
    def events(self) -> list[cqrs.Event]:
        return list(self._events)

    async def _complete_with_retry(self, *, system: str, user: str, attempts: int = 4) -> str:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await self._language_model.complete(system=system, user=user)
            except (httpx.HTTPError, ValueError, TimeoutError) as exc:
                last_error = exc
                await asyncio.sleep(min(2**attempt, 20))
        assert last_error is not None
        raise last_error

    async def _search_one(self, query: str, *, per_platform: int) -> list[VideoSearchHit]:
        async with self._search_sema:

            async def youtube() -> list[VideoSearchHit]:
                try:
                    return list(await self._youtube_search.search(query, limit=per_platform))
                except Exception:
                    return []

            async def rutube() -> list[VideoSearchHit]:
                try:
                    return list(await self._rutube_search.search(query, limit=per_platform))
                except Exception:
                    return []

            yt_hits, rt_hits = await asyncio.gather(youtube(), rutube())
            return [*yt_hits, *rt_hits]

    async def _search_videos(self, queries: list[str], *, per_platform: int) -> list[VideoSearchHit]:
        batches = await asyncio.gather(
            *(self._search_one(query, per_platform=per_platform) for query in queries),
        )
        hits: list[VideoSearchHit] = []
        for batch in batches:
            hits.extend(batch)
        return hits

    async def handle(self, request: EnrichExerciseCatalogCommand) -> EnrichExerciseCatalogResult:
        store = load_exercises_jsonl(request.exercises_jsonl_path)
        if not store:
            raise FileNotFoundError(f"catalog JSONL empty or missing: {request.exercises_jsonl_path}")

        candidates = [
            record
            for record in sorted(store.values(), key=lambda item: item.name_normalized)
            if _needs_enrichment(
                record,
                only_short_technique=request.only_short_technique,
                short_technique_chars=request.short_technique_chars,
                only_missing_videos=request.only_missing_videos,
            )
        ]
        if request.limit is not None:
            candidates = candidates[: max(0, request.limit)]

        system = load_system_prompt()
        per_platform = request.max_videos_per_platform
        batch_size = max(1, request.batch_size)
        updated = 0

        for offset in range(0, len(candidates), batch_size):
            batch = candidates[offset : offset + batch_size]
            expected_names = {record.name for record in batch}
            payload = [
                {
                    "name": record.name,
                    "primary_muscles": record.primary_muscles,
                    "secondary_muscles": record.secondary_muscles,
                    "technique": record.technique,
                }
                for record in batch
            ]
            user_prompt = render_prompt(
                "catalog_enrich.md",
                exercises_json=json.dumps(payload, ensure_ascii=False),
            )
            try:
                raw = await self._complete_with_retry(system=system, user=user_prompt)
                items = _parse_enrich_items(extract_json_array(raw), expected_names=expected_names)
            except Exception as exc:
                print(
                    f"batch {offset // batch_size + 1}: LLM failed ({exc!r}); skipping technique rewrite",
                    file=sys.stderr,
                )
                items = []
            by_name = {item["name"]: item for item in items}

            async def enrich_one(record: ExerciseJsonlRecord) -> ExerciseJsonlRecord:
                item = by_name.get(record.name)
                technique = item["technique"] if item else record.technique
                queries = item["video_queries"] if item else [f"{record.name} техника"]
                hits = await self._search_videos(queries, per_platform=per_platform)
                hits = filter_relevant_video_hits(hits, exercise_name=record.name)
                videos = dedupe_videos(hits, limit_per_platform=per_platform)
                if not videos and record.videos:
                    videos = list(record.videos)
                return ExerciseJsonlRecord(
                    name=record.name,
                    primary_muscles=list(record.primary_muscles),
                    secondary_muscles=list(record.secondary_muscles),
                    technique=technique,
                    videos=videos,
                )

            enriched = await asyncio.gather(*(enrich_one(record) for record in batch))
            for record in enriched:
                upsert_exercise(store, record)
                updated += 1

            write_exercises_jsonl(request.exercises_jsonl_path, store.values())
            print(
                f"enriched {min(offset + batch_size, len(candidates))}/{len(candidates)}",
                flush=True,
            )

        return EnrichExerciseCatalogResult(
            exercises_processed=len(candidates),
            exercises_updated=updated,
            path=str(request.exercises_jsonl_path),
        )
