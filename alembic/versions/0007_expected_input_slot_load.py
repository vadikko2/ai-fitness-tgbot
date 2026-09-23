"""Allow slot_weight and slot_load in users.expected_input check.

Revision ID: 0007_expected_input_slot_load
Revises: 0006_day_warmup_cooldown
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_expected_input_slot_load"
down_revision: str | None = "0006_day_warmup_cooldown"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("alter table users drop constraint if exists users_expected_input_check")
    op.execute(
        """
        alter table users
            add constraint users_expected_input_check check (
                expected_input in (
                    'none',
                    'profile_field',
                    'weight',
                    'measurement_value',
                    'proposal_utterance',
                    'completion_deviation',
                    'technique_video',
                    'slot_weight',
                    'slot_load'
                )
            )
        """,
    )


def downgrade() -> None:
    op.execute("alter table users drop constraint if exists users_expected_input_check")
    op.execute(
        """
        alter table users
            add constraint users_expected_input_check check (
                expected_input in (
                    'none',
                    'profile_field',
                    'weight',
                    'measurement_value',
                    'proposal_utterance',
                    'completion_deviation',
                    'technique_video'
                )
            )
        """,
    )
