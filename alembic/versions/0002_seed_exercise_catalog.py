"""Seed exercise catalog from data/exercises.jsonl.

Revision ID: 0002_seed_exercise_catalog
Revises: 0001_initial_schema
Create Date: 2026-09-22

Alembic branch label: catalog (merge with Stage 2 heads later if needed).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import text

from alembic import op
from fitness_bot.domain.catalog.normalize import normalize_exercise_name
from fitness_bot.infrastructure.db.seed_exercise_catalog import (
    load_catalog_jsonl_records,
    seed_exercise_catalog,
)

revision: str = "0002_seed_exercise_catalog"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = ("catalog",)
depends_on: str | Sequence[str] | None = None

REPO_ROOT = Path(__file__).resolve().parents[2]
JSONL_PATH = REPO_ROOT / "data" / "exercises.jsonl"


def upgrade() -> None:
    seed_exercise_catalog(op.get_bind(), JSONL_PATH)


def downgrade() -> None:
    conn = op.get_bind()
    for raw in load_catalog_jsonl_records(JSONL_PATH):
        name_normalized = normalize_exercise_name(str(raw["name"]).strip())
        row = conn.execute(
            text("select id from exercises where name_normalized = :name_normalized"),
            {"name_normalized": name_normalized},
        ).first()
        if row is None:
            continue
        exercise_id = row[0]
        conn.execute(text("delete from exercise_videos where exercise_id = :id"), {"id": exercise_id})
        conn.execute(text("delete from exercise_muscles where exercise_id = :id"), {"id": exercise_id})
        conn.execute(text("delete from exercises where id = :id"), {"id": exercise_id})
