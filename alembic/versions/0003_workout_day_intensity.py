"""Add intensity column to workout_days.

Revision ID: 0003_workout_day_intensity
Revises: 0002_seed_exercise_catalog
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_workout_day_intensity"
down_revision: str | None = "0002_seed_exercise_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        alter table workout_days
            add column intensity text not null default 'medium'
            check (intensity in ('recovery', 'light', 'medium', 'heavy'));
        """,
    )
    op.execute(
        """
        comment on column workout_days.intensity is
            'Интенсивность дня: recovery / light / medium / heavy.';
        """,
    )


def downgrade() -> None:
    op.execute("alter table workout_days drop column if exists intensity;")
