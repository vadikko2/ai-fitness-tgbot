"""Move training_style from program to workout_days.

Revision ID: 0005_day_training_style
Revises: 0004_program_types_taxonomy
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_day_training_style"
down_revision: str | None = "0004_program_types_taxonomy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRAINING_STYLES = ("classic", "strength", "circuit", "hit")
_STYLE_CHECK = ", ".join(f"'{value}'" for value in _TRAINING_STYLES)


def upgrade() -> None:
    op.execute(
        f"""
        alter table workout_days
            add column if not exists training_style text not null default 'classic'
            check (training_style in ({_STYLE_CHECK}));
        """,
    )
    op.execute(
        """
        update workout_days wd
        set training_style = p.training_style
        from programs p
        where wd.program_id = p.id
          and p.training_style is not null;
        """,
    )
    op.execute(
        """
        update workout_days wd
        set training_style = pr.training_style
        from proposals pr
        where wd.proposal_id = pr.id
          and pr.training_style is not null;
        """,
    )
    op.execute(
        """
        comment on column workout_days.training_style is
            'Стиль нагрузки дня: classic / strength / circuit / hit.';
        """,
    )
    op.execute("alter table proposals drop column if exists training_style;")
    op.execute("alter table programs drop column if exists training_style;")


def downgrade() -> None:
    op.execute(
        f"""
        alter table programs
            add column if not exists training_style text not null default 'classic'
            check (training_style in ({_STYLE_CHECK}));
        """,
    )
    op.execute(
        f"""
        alter table proposals
            add column if not exists training_style text
            check (training_style is null or training_style in ({_STYLE_CHECK}));
        """,
    )
    op.execute("alter table workout_days drop column if exists training_style;")
