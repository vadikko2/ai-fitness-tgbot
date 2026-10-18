"""Persist wellbeing → proposal link and index wellbeing history.

Revision ID: 0017_wellbeing_tracking
Revises: 0016_places_program_types
Create Date: 2026-10-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_wellbeing_tracking"
down_revision: str | None = "0016_places_program_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        alter table wellbeing_entries
            add column if not exists proposal_id uuid null
                references proposals(id) on delete set null;
        """,
    )
    op.execute(
        """
        comment on column wellbeing_entries.proposal_id is
            'Черновик, в который подана отметка; при подтверждении черновика отметка помечается учтённой.';
        """,
    )
    op.execute(
        "create index if not exists ix_wellbeing_entries_user_created "
        "on wellbeing_entries (user_id, created_at desc);",
    )
    op.execute(
        "create index if not exists ix_wellbeing_entries_proposal "
        "on wellbeing_entries (proposal_id) where proposal_id is not null;",
    )


def downgrade() -> None:
    op.execute("drop index if exists ix_wellbeing_entries_proposal;")
    op.execute("drop index if exists ix_wellbeing_entries_user_created;")
    op.execute("alter table wellbeing_entries drop column if exists proposal_id;")
