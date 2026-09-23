"""Expand goal check constraints with recovery, stay_fit, healthy_lifestyle.

Revision ID: 0009_expand_goal_values
Revises: 0008_profile_fields_mvp
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_expand_goal_values"
down_revision: str | None = "0008_profile_fields_mvp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GOALS = (
    "fat_loss",
    "muscle_gain",
    "strength",
    "maintenance",
    "recovery",
    "stay_fit",
    "healthy_lifestyle",
)
_LEGACY_GOALS = ("fat_loss", "muscle_gain", "strength", "maintenance")
_GOAL_CHECK = ", ".join(f"'{value}'" for value in _GOALS)
_LEGACY_GOAL_CHECK = ", ".join(f"'{value}'" for value in _LEGACY_GOALS)


def upgrade() -> None:
    op.execute("alter table users drop constraint if exists users_goal_check;")
    op.execute(
        f"alter table users add constraint users_goal_check check (goal is null or goal in ({_GOAL_CHECK}));",
    )
    op.execute("alter table nutrition_recommendations drop constraint if exists nutrition_recommendations_goal_check;")
    op.execute(
        f"alter table nutrition_recommendations add constraint nutrition_recommendations_goal_check "
        f"check (goal in ({_GOAL_CHECK}));",
    )
    op.execute(
        """
        comment on column users.goal is
            'Одна активная цель: fat_loss, muscle_gain, strength, maintenance, recovery, stay_fit или healthy_lifestyle.';
        """,
    )


def downgrade() -> None:
    op.execute(
        """
        update users
        set goal = 'maintenance'
        where goal in ('recovery', 'stay_fit', 'healthy_lifestyle');
        """,
    )
    op.execute(
        """
        update nutrition_recommendations
        set goal = 'maintenance'
        where goal in ('recovery', 'stay_fit', 'healthy_lifestyle');
        """,
    )
    op.execute("alter table users drop constraint if exists users_goal_check;")
    op.execute(
        f"alter table users add constraint users_goal_check check (goal is null or goal in ({_LEGACY_GOAL_CHECK}));",
    )
    op.execute("alter table nutrition_recommendations drop constraint if exists nutrition_recommendations_goal_check;")
    op.execute(
        f"alter table nutrition_recommendations add constraint nutrition_recommendations_goal_check "
        f"check (goal in ({_LEGACY_GOAL_CHECK}));",
    )
    op.execute(
        """
        comment on column users.goal is
            'Одна активная цель: fat_loss, muscle_gain, strength или maintenance.';
        """,
    )
