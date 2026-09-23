from __future__ import annotations

import argparse

from fitness_bot.presentation.cli import enrich_catalog, load_catalog, seed_catalog, seed_guides


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fitness bot CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    seed_guides_parser = sub.add_parser("seed-guides", help="C1: seed fixed measurement guides")
    seed_guides_parser.add_argument(
        "--offline",
        action="store_true",
        help="Use deterministic Russian instructions without LanguageModel API",
    )

    seed_catalog_parser = sub.add_parser("seed-catalog", help="C2: seed exercises.jsonl via LLM + video search")
    seed_catalog_parser.add_argument("--muscle-groups", default=None)
    seed_catalog_parser.add_argument("--exercises-jsonl", default=None)
    seed_catalog_parser.add_argument("--max-videos", type=int, default=5)

    enrich_catalog_parser = sub.add_parser(
        "enrich-catalog",
        help="Rewrite technique + attach videos for existing exercises.jsonl",
    )
    enrich_catalog_parser.add_argument("--exercises-jsonl", default=None)
    enrich_catalog_parser.add_argument("--max-videos", type=int, default=5)
    enrich_catalog_parser.add_argument("--batch-size", type=int, default=5)
    enrich_catalog_parser.add_argument("--only-short-technique", action="store_true")
    enrich_catalog_parser.add_argument("--short-technique-chars", type=int, default=120)
    enrich_catalog_parser.add_argument("--only-missing-videos", action="store_true")
    enrich_catalog_parser.add_argument("--limit", type=int, default=None)

    load_catalog_parser = sub.add_parser(
        "load-catalog",
        help="Upsert data/exercises.jsonl into Postgres (idempotent; same as Alembic 0002)",
    )
    load_catalog_parser.add_argument("--exercises-jsonl", default=None)
    load_catalog_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "seed-guides":
        seed_guides.main(["--offline"] if args.offline else [])
        return
    if args.command == "seed-catalog":
        catalog_argv: list[str] = []
        if args.muscle_groups is not None:
            catalog_argv.extend(["--muscle-groups", str(args.muscle_groups)])
        if args.exercises_jsonl is not None:
            catalog_argv.extend(["--exercises-jsonl", str(args.exercises_jsonl)])
        catalog_argv.extend(["--max-videos", str(args.max_videos)])
        seed_catalog.main(catalog_argv)
        return
    if args.command == "enrich-catalog":
        enrich_argv: list[str] = []
        if args.exercises_jsonl is not None:
            enrich_argv.extend(["--exercises-jsonl", str(args.exercises_jsonl)])
        enrich_argv.extend(["--max-videos", str(args.max_videos)])
        enrich_argv.extend(["--batch-size", str(args.batch_size)])
        enrich_argv.extend(["--short-technique-chars", str(args.short_technique_chars)])
        if args.only_short_technique:
            enrich_argv.append("--only-short-technique")
        if args.only_missing_videos:
            enrich_argv.append("--only-missing-videos")
        if args.limit is not None:
            enrich_argv.extend(["--limit", str(args.limit)])
        enrich_catalog.main(enrich_argv)
        return
    if args.command == "load-catalog":
        load_argv: list[str] = []
        if args.exercises_jsonl is not None:
            load_argv.extend(["--exercises-jsonl", str(args.exercises_jsonl)])
        if args.dry_run:
            load_argv.append("--dry-run")
        load_catalog.main(load_argv)
