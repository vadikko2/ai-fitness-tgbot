from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

import httpx

from fitness_bot.infrastructure.adapters.language_model import TimewebLanguageModel
from fitness_bot.infrastructure.adapters.rutube_search import RutubeApiSearch
from fitness_bot.infrastructure.adapters.youtube_search import YouTubeDataApiSearch
from fitness_bot.service.handlers.commands.enrich_exercise_catalog import EnrichExerciseCatalogCommandHandler
from fitness_bot.service.models.commands.enrich_exercise_catalog import EnrichExerciseCatalogCommand
from fitness_bot.service.ports.video_search import VideoSearchHit, YouTubeSearch
from fitness_bot.shared.paths import EXERCISES_JSONL_PATH
from fitness_bot.shared.settings import load_settings


class _EmptyYouTubeSearch(YouTubeSearch):
    async def search(self, query: str, *, limit: int = 5) -> Sequence[VideoSearchHit]:
        return []


def _youtube_search(api_key: str) -> YouTubeSearch:
    key = api_key.strip()
    if not key or key.lower() in {"placeholder", "changeme", "your_key_here"}:
        return _EmptyYouTubeSearch()
    return YouTubeDataApiSearch(key)


async def _run(args: argparse.Namespace) -> int:
    settings = load_settings()
    missing: list[str] = []
    if not settings.timeweb_api_key.strip():
        missing.append("TIMEWEB_API_KEY")
    if not settings.timeweb_base_url.strip():
        missing.append("TIMEWEB_BASE_URL")
    if missing:
        print(
            "EnrichExerciseCatalogCommand needs TIMEWEB keys for LLM. "
            f"Missing or empty: {', '.join(missing)}. "
            "YouTube is optional; Rutube uses the public search API.",
            file=sys.stderr,
        )
        return 2

    language_model = TimewebLanguageModel(
        api_key=settings.timeweb_api_key,
        base_url=settings.timeweb_base_url,
    )
    youtube = _youtube_search(settings.youtube_api_key)
    rutube = RutubeApiSearch()
    handler = EnrichExerciseCatalogCommandHandler(language_model, youtube, rutube)
    try:
        try:
            result = await handler.handle(
                EnrichExerciseCatalogCommand(
                    exercises_jsonl_path=args.exercises_jsonl,
                    max_videos_per_platform=args.max_videos,
                    batch_size=args.batch_size,
                    only_short_technique=args.only_short_technique,
                    short_technique_chars=args.short_technique_chars,
                    only_missing_videos=args.only_missing_videos,
                    limit=args.limit,
                ),
            )
        except (FileNotFoundError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 4
        except httpx.HTTPError as exc:
            detail = str(exc).strip() or repr(exc)
            response = getattr(exc, "response", None)
            if response is not None:
                detail = f"{detail} status={response.status_code} body={response.text[:300]!r}"
            print(
                "Enrich failed calling LLM or video search APIs. "
                f"{detail}. "
                "Check TIMEWEB_BASE_URL, TIMEWEB_API_KEY, and optionally YOUTUBE_API_KEY.",
                file=sys.stderr,
            )
            return 3
    finally:
        await language_model.aclose()
        close = getattr(youtube, "aclose", None)
        if close is not None:
            await close()
        await rutube.aclose()

    print(
        f"Enriched {result.exercises_updated}/{result.exercises_processed} exercises in {result.path}",
    )
    if isinstance(youtube, _EmptyYouTubeSearch):
        print(
            "Note: YOUTUBE_API_KEY is missing/placeholder; attached Rutube videos only.",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Rewrite technique + attach YouTube/Rutube videos for existing exercises.jsonl",
    )
    parser.add_argument("--exercises-jsonl", type=Path, default=EXERCISES_JSONL_PATH)
    parser.add_argument("--max-videos", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--only-short-technique", action="store_true")
    parser.add_argument("--short-technique-chars", type=int, default=120)
    parser.add_argument("--only-missing-videos", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
