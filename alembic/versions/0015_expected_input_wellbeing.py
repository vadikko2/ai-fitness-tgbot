"""Allow wellbeing in users.expected_input check.

Revision ID: 0015_expected_input_wellbeing
Revises: 0014_training_place_wellbeing
Create Date: 2026-09-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_expected_input_wellbeing"
down_revision: str | None = "0014_training_place_wellbeing"
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
    "progress_photo",
    "wellbeing",
    "feedback_text",
    "feedback_photo",
    "feedback_cancel_reply",
)

# State after 0012_feedback_tickets (0013/0014 did not change this check).
_PREVIOUS_EXPECTED_INPUTS = tuple(v for v in EXPECTED_INPUTS if v != "wellbeing")

_CHECK = ", ".join(f"'{value}'" for value in EXPECTED_INPUTS)
_PREVIOUS_CHECK = ", ".join(f"'{value}'" for value in _PREVIOUS_EXPECTED_INPUTS)


def upgrade() -> None:
    op.execute("alter table users drop constraint if exists users_expected_input_check")
    op.execute(
        f"alter table users add constraint users_expected_input_check "
        f"check (expected_input in ({_CHECK}))",
    )


def downgrade() -> None:
    op.execute(
        f"""
        update users
        set expected_input = 'none',
            expected_field = null,
            expected_payload = '{{}}'::jsonb
        where expected_input not in ({_PREVIOUS_CHECK})
        """,
    )
    op.execute("alter table users drop constraint if exists users_expected_input_check")
    op.execute(
        f"alter table users add constraint users_expected_input_check "
        f"check (expected_input in ({_PREVIOUS_CHECK}))",
    )
