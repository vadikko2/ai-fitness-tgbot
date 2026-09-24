"""Ideas and problem reports.

Revision ID: 0012_feedback_tickets
Revises: 0011_progress_photos
Create Date: 2026-09-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_feedback_tickets"
down_revision: str | None = "0011_progress_photos"
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
    "feedback_text",
    "feedback_photo",
    "feedback_cancel_reply",
)

_PREVIOUS_EXPECTED_INPUTS = EXPECTED_INPUTS[: len(EXPECTED_INPUTS) - 3]

_CHECK = ", ".join(f"'{value}'" for value in EXPECTED_INPUTS)
_PREVIOUS_CHECK = ", ".join(f"'{value}'" for value in _PREVIOUS_EXPECTED_INPUTS)


def upgrade() -> None:
    op.execute("alter table users drop constraint if exists users_expected_input_check")
    op.execute(
        f"alter table users add constraint users_expected_input_check "
        f"check (expected_input in ({_CHECK}))",
    )
    op.execute(
        """
        create table feedback_tickets (
            id uuid primary key default gen_random_uuid(),
            author_user_id uuid not null references users (id) on delete cascade,
            kind text not null check (kind in ('idea', 'problem')),
            body text not null,
            status text not null default 'draft'
                check (status in ('draft', 'new', 'in_progress', 'resolved', 'cancelled')),
            moderator_reply text,
            resolved_by_user_id uuid references users (id),
            photo_file_ids text not null default '[]',
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            resolved_at timestamptz
        );

        create index ix_feedback_tickets_author_kind_created
            on feedback_tickets (author_user_id, kind, created_at desc);

        create table feedback_moderator_messages (
            id uuid primary key default gen_random_uuid(),
            ticket_id uuid not null references feedback_tickets (id) on delete cascade,
            moderator_user_id uuid not null references users (id) on delete cascade,
            chat_id bigint not null,
            message_id bigint not null,
            created_at timestamptz not null default now()
        );

        create index ix_feedback_moderator_messages_ticket
            on feedback_moderator_messages (ticket_id);

        comment on table feedback_tickets is
            'Идеи и сообщения о проблемах. Черновик не виден в списке, пока пользователь не нажмёт «Отправить».';
        comment on column feedback_tickets.photo_file_ids is
            'JSON-массив telegram file_id, не больше трёх.';
        comment on table feedback_moderator_messages is
            'Копии сообщения модераторам, чтобы обновить текст при смене статуса.';
        """,
    )


def downgrade() -> None:
    op.execute(
        """
        drop table if exists feedback_moderator_messages cascade;
        drop table if exists feedback_tickets cascade;
        """,
    )
    op.execute(
        f"""
        update users
        set expected_input = 'none',
            expected_field = null,
            focus_slot = null
        where expected_input not in ({_PREVIOUS_CHECK})
        """,
    )
    op.execute("alter table users drop constraint if exists users_expected_input_check")
    op.execute(
        f"alter table users add constraint users_expected_input_check "
        f"check (expected_input in ({_PREVIOUS_CHECK}))",
    )
