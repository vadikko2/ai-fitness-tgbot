"""Add training_place, nutrition_constraints, and wellbeing_entries.

Revision ID: 0014_training_place_wellbeing
Revises: 0013_nutrition_sports_nutrition
Create Date: 2026-09-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_training_place_wellbeing"
down_revision: str | None = "0013_nutrition_sports_nutrition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        alter table users
            add column if not exists training_place text
                check (
                    training_place is null
                    or training_place in ('gym', 'home', 'outdoor', 'mixed')
                ),
            add column if not exists nutrition_constraints text;
        """,
    )
    op.execute(
        """
        comment on column users.training_place is
            'Место занятий: gym / home / outdoor / mixed.';
        comment on column users.nutrition_constraints is
            'Жёсткие пищевые ограничения: болезни, аллергии, противопоказания.';
        """,
    )
    op.execute(
        """
        create table if not exists wellbeing_entries (
            id uuid primary key default gen_random_uuid(),
            user_id uuid not null references users(id) on delete cascade,
            text text not null,
            created_at timestamptz not null default now(),
            applied_at timestamptz
        );
        """,
    )
    op.execute(
        """
        create index if not exists wellbeing_entries_user_created_idx
            on wellbeing_entries (user_id, created_at desc);
        create index if not exists wellbeing_entries_user_unapplied_idx
            on wellbeing_entries (user_id)
            where applied_at is null;
        """,
    )
    op.execute(
        """
        comment on table wellbeing_entries is
            'История самочувствия пользователя (свободный текст).';
        comment on column wellbeing_entries.applied_at is
            'Когда запись учли при адаптации тренировки; null = ещё не учтена.';
        """,
    )


def downgrade() -> None:
    op.execute("drop table if exists wellbeing_entries;")
    op.execute(
        """
        alter table users
            drop column if exists nutrition_constraints,
            drop column if exists training_place;
        """,
    )
