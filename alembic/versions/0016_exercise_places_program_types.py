"""Add exercise places and expand program_type taxonomy.

Revision ID: 0016_exercise_places_program_types
Revises: 0015_expected_input_wellbeing
Create Date: 2026-09-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016_exercise_places_program_types"
down_revision: str | None = "0015_expected_input_wellbeing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROGRAM_TYPES = (
    "full_body",
    "upper_lower",
    "push_pull",
    "antagonist",
    "synergist",
    "split",
    "kettlebell",
    "cardio",
    "bodyweight_recovery",
    "stretching",
)
_PROGRAM_TYPE_CHECK = ", ".join(f"'{value}'" for value in _PROGRAM_TYPES)
_OLD_PROGRAM_TYPES = (
    "full_body",
    "upper_lower",
    "push_pull",
    "antagonist",
    "synergist",
    "split",
)
_OLD_PROGRAM_TYPE_CHECK = ", ".join(f"'{value}'" for value in _OLD_PROGRAM_TYPES)


def upgrade() -> None:
    op.execute(
        """
        alter table exercises
            add column if not exists places text[] not null default array['gym']::text[];
        """,
    )
    op.execute(
        """
        alter table exercises drop constraint if exists exercises_places_check;
        alter table exercises
            add constraint exercises_places_check
            check (
                places <> '{}'
                and places <@ array['gym', 'home', 'outdoor']::text[]
            );
        """,
    )
    op.execute(
        """
        comment on column exercises.places is
            'Где можно выполнять: gym / home / outdoor (несколько значений).';
        """,
    )
    op.execute("alter table programs drop constraint if exists programs_program_type_check;")
    op.execute("alter table proposals drop constraint if exists proposals_program_type_check;")
    op.execute(
        f"alter table programs add constraint programs_program_type_check "
        f"check (program_type in ({_PROGRAM_TYPE_CHECK}));",
    )
    op.execute(
        f"alter table proposals add constraint proposals_program_type_check "
        f"check (program_type is null or program_type in ({_PROGRAM_TYPE_CHECK}));",
    )


def downgrade() -> None:
    op.execute("alter table programs drop constraint if exists programs_program_type_check;")
    op.execute("alter table proposals drop constraint if exists proposals_program_type_check;")
    op.execute(
        f"alter table programs add constraint programs_program_type_check "
        f"check (program_type in ({_OLD_PROGRAM_TYPE_CHECK}));",
    )
    op.execute(
        f"alter table proposals add constraint proposals_program_type_check "
        f"check (program_type is null or program_type in ({_OLD_PROGRAM_TYPE_CHECK}));",
    )
    op.execute("alter table exercises drop constraint if exists exercises_places_check;")
    op.execute("alter table exercises drop column if exists places;")
