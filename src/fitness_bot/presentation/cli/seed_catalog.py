from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

from fitness_bot.infrastructure.adapters.language_model import TimewebLanguageModel
from fitness_bot.infrastructure.adapters.rutube_search import RutubeApiSearch
from fitness_bot.infrastructure.adapters.youtube_search import YouTubeDataApiSearch
from fitness_bot.service.handlers.commands.seed_exercise_catalog import SeedExerciseCatalogCommandHandler
from fitness_bot.service.models.commands.seed_exercise_catalog import SeedExerciseCatalogCommand
from fitness_bot.shared.paths import EXERCISES_JSONL_PATH, MUSCLE_GROUPS_PATH
from fitness_bot.shared.settings import load_settings


async def _run(args: argparse.Namespace) -> int:
    settings = load_settings()
    missing: list[str] = []
    if not settings.timeweb_api_key.strip():
        missing.append("TIMEWEB_API_KEY")
    if not settings.timeweb_base_url.strip():
        missing.append("TIMEWEB_BASE_URL")
    if not settings.youtube_api_key.strip():
        missing.append("YOUTUBE_API_KEY")
    if missing:
        print(
            "C2 SeedExerciseCatalogCommand needs API keys for LLM and YouTube search. "
            f"Missing or empty: {', '.join(missing)}. "
            "Rutube uses the public search API (no key). "
            "A starter catalog is already in data/exercises.jsonl for Alembic.",
            file=sys.stderr,
        )
        return 2

    language_model = TimewebLanguageModel(
        api_key=settings.timeweb_api_key,
        base_url=settings.timeweb_base_url,
    )
    youtube = YouTubeDataApiSearch(settings.youtube_api_key)
    rutube = RutubeApiSearch()
    handler = SeedExerciseCatalogCommandHandler(language_model, youtube, rutube)
    try:
        try:
            result = await handler.handle(
                SeedExerciseCatalogCommand(
                    muscle_groups_path=args.muscle_groups,
                    exercises_jsonl_path=args.exercises_jsonl,
                    max_videos_per_platform=args.max_videos,
                ),
            )
        except httpx.HTTPError as exc:
            print(
                "C2 failed calling LLM or video search APIs. "
                f"{exc}. "
                "Check TIMEWEB_BASE_URL (OpenAI-compatible root ending before /chat/completions), "
                "TIMEWEB_API_KEY, and YOUTUBE_API_KEY. "
                "Starter data/exercises.jsonl remains valid for alembic upgrade.",
                file=sys.stderr,
            )
            return 3
    finally:
        await language_model.aclose()
        await youtube.aclose()
        await rutube.aclose()

    print(
        f"Wrote {result.exercises_written} exercises from {result.muscle_groups} muscle groups to {result.path}",
    )
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="C2: seed data/exercises.jsonl via catalog_author + video search")
    parser.add_argument("--muscle-groups", type=Path, default=MUSCLE_GROUPS_PATH)
    parser.add_argument("--exercises-jsonl", type=Path, default=EXERCISES_JSONL_PATH)
    parser.add_argument("--max-videos", type=int, default=5)
    args = parser.parse_args(argv)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
