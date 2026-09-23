"""Expand program_type values and add training_style.

Revision ID: 0004_program_types_taxonomy
Revises: 0003_workout_day_intensity
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_program_types_taxonomy"
down_revision: str | None = "0003_workout_day_intensity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROGRAM_TYPES = (
    "full_body",
    "upper_lower",
    "push_pull",
    "antagonist",
    "synergist",
    "split",
)
_TRAINING_STYLES = ("classic", "strength", "circuit", "hit")
_PROGRAM_TYPE_CHECK = ", ".join(f"'{value}'" for value in _PROGRAM_TYPES)
_STYLE_CHECK = ", ".join(f"'{value}'" for value in _TRAINING_STYLES)


def upgrade() -> None:
    op.execute("alter table programs drop constraint if exists programs_program_type_check;")
    op.execute("alter table proposals drop constraint if exists proposals_program_type_check;")
    op.execute(f"alter table programs add constraint programs_program_type_check check (program_type in ({_PROGRAM_TYPE_CHECK}));")
    op.execute(f"alter table proposals add constraint proposals_program_type_check check (program_type is null or program_type in ({_PROGRAM_TYPE_CHECK}));")
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
    op.execute(
        """
        comment on column programs.training_style is
            'Стиль нагрузки: classic / strength / circuit / hit.';
        """,
    )
    op.execute(
        """
        comment on column proposals.training_style is
            'Стиль нагрузки для черновика программы; classic / strength / circuit / hit.';
        """,
    )
    op.execute(
        """
        comment on column programs.program_type is
            'Структура недели: full_body, upper_lower, push_pull, antagonist, synergist, split.';
        """,
    )
    op.execute(
        """
        comment on column proposals.program_type is
            'Структура недели; заполнен при kind = program.';
        """,
    )


def downgrade() -> None:
    op.execute("alter table proposals drop column if exists training_style;")
    op.execute("alter table programs drop column if exists training_style;")
    op.execute("alter table programs drop constraint if exists programs_program_type_check;")
    op.execute("alter table proposals drop constraint if exists proposals_program_type_check;")
    op.execute("alter table programs add constraint programs_program_type_check check (program_type in ('split', 'full_body', 'push_pull'));")
    op.execute(
        "alter table proposals add constraint proposals_program_type_check check (program_type is null or program_type in ('split', 'full_body', 'push_pull'));",
    )
