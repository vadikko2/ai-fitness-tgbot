"""Add warmup and cooldown text columns to workout_days.

Revision ID: 0006_day_warmup_cooldown
Revises: 0005_day_training_style
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_day_warmup_cooldown"
down_revision: str | None = "0005_day_training_style"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        alter table workout_days
            add column if not exists warmup text not null default '',
            add column if not exists cooldown text not null default '';
        """,
    )
    op.execute(
        """
        comment on column workout_days.warmup is
            'Текстовая разминка дня (не слот упражнений).';
        """,
    )
    op.execute(
        """
        comment on column workout_days.cooldown is
            'Текстовая заминка дня (не слот упражнений).';
        """,
    )


def downgrade() -> None:
    op.execute("alter table workout_days drop column if exists cooldown;")
    op.execute("alter table workout_days drop column if exists warmup;")
