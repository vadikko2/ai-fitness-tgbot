"""Load data/exercises.jsonl into Postgres (idempotent upsert)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from fitness_bot.infrastructure.db.seed_exercise_catalog import (
    load_catalog_jsonl_records,
    seed_exercise_catalog,
)
from fitness_bot.shared.paths import EXERCISES_JSONL_PATH
from fitness_bot.shared.settings import load_settings


def _sync_database_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql+asyncpg://")
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Upsert exercise catalog from JSONL into Postgres (same logic as Alembic 0002)",
    )
    parser.add_argument("--exercises-jsonl", type=Path, default=EXERCISES_JSONL_PATH)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse JSONL and print counts without writing to the database",
    )
    args = parser.parse_args(argv)

    try:
        records = load_catalog_jsonl_records(args.exercises_jsonl)
        if args.dry_run:
            print(f"dry-run: would upsert {len(records)} exercises from {args.exercises_jsonl}")
            raise SystemExit(0)

        settings = load_settings()
        engine = create_engine(_sync_database_url(settings.database_url))
        with engine.begin() as conn:
            upserted = seed_exercise_catalog(conn, args.exercises_jsonl)
            total = conn.execute(text("select count(*) from exercises")).scalar_one()
        print(f"upserted={upserted} exercises_total={total} path={args.exercises_jsonl}")
    except SystemExit:
        raise
    except Exception as exc:
        print(f"load-catalog failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
