"""Expand users.expected_input check to all ExpectedInput values.

Revision ID: 0011_expand_expected_input
Revises: 0010_coach_and_program_library
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_expand_expected_input"
down_revision: str | None = "0010_coach_and_program_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep in sync with fitness_bot.domain.enums.ExpectedInput
EXPECTED_INPUTS = (
    "none",
    "profile_field",
    "weight",
    "measurement_value",
    "proposal_utterance",
    "completion_deviation",
    "technique_video",
    "slot_weight",
    "slot_load",
    "code_or_link",
    "coach_note",
    "coach_feedback",
    "coach_application",
    "coach_credential",
    "moderator_reject_comment",
    "coach_review",
    "coach_report",
    "coach_edit_client",
)

# State after 0007_expected_input_slot_load (0010 did not change this check).
_LEGACY_EXPECTED_INPUTS = (
    "none",
    "profile_field",
    "weight",
    "measurement_value",
    "proposal_utterance",
    "completion_deviation",
    "technique_video",
    "slot_weight",
    "slot_load",
)

_CHECK = ", ".join(f"'{value}'" for value in EXPECTED_INPUTS)
_LEGACY_CHECK = ", ".join(f"'{value}'" for value in _LEGACY_EXPECTED_INPUTS)


def upgrade() -> None:
    op.execute("alter table users drop constraint if exists users_expected_input_check")
    op.execute(
        f"alter table users add constraint users_expected_input_check "
        f"check (expected_input in ({_CHECK}))",
    )


def downgrade() -> None:
    op.execute(
        """
        update users
        set expected_input = 'none',
            expected_field = null,
            focus_slot = null
        where expected_input not in (
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
        """,
    )
    op.execute("alter table users drop constraint if exists users_expected_input_check")
    op.execute(
        f"alter table users add constraint users_expected_input_check "
        f"check (expected_input in ({_LEGACY_CHECK}))",
    )
