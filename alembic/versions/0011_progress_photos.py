"""Progress photos + expand users.expected_input check.

Revision ID: 0011_progress_photos
Revises: 0010_coach_and_program_library
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_progress_photos"
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
    "progress_photo",
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

    op.execute(
        """
        create table progress_photo_sets (
            id uuid primary key default gen_random_uuid(),
            user_id uuid not null references users (id) on delete cascade,
            captured_at timestamptz not null default now(),
            local_date date not null,
            complete boolean not null default false,
            unique (user_id, local_date)
        );

        create index ix_progress_photo_sets_user_date
            on progress_photo_sets (user_id, local_date desc);

        create table progress_photos (
            id uuid primary key default gen_random_uuid(),
            set_id uuid not null references progress_photo_sets (id) on delete cascade,
            angle text not null check (angle in ('front', 'side', 'back')),
            object_key text not null,
            content_type text not null check (content_type like 'image/%%'),
            byte_size integer not null check (byte_size > 0 and byte_size <= 10485760),
            telegram_file_id text,
            unique (set_id, angle),
            unique (object_key)
        );

        create index ix_progress_photos_set on progress_photos (set_id);

        create table progress_photo_reminders (
            user_id uuid primary key references users (id) on delete cascade,
            local_time time not null,
            last_sent_on date
        );

        create table progress_photo_reminder_weekdays (
            user_id uuid not null references progress_photo_reminders (user_id) on delete cascade,
            weekday smallint not null check (weekday between 1 and 7),
            primary key (user_id, weekday)
        );

        comment on table progress_photo_sets is
            'Один набор из трёх ракурсов прогресса на локальный день пользователя.';
        comment on column progress_photo_sets.local_date is
            'Локальная календарная дата съёмки в поясе пользователя.';
        comment on column progress_photo_sets.complete is
            'True, когда сохранены front, side и back.';
        comment on table progress_photos is
            'Фото одного ракурса в наборе. Файл лежит в S3.';
        comment on column progress_photos.object_key is
            'Ключ: users/{user_id}/progress_photos/{set_id}/{angle}.jpg';
        comment on column progress_photos.telegram_file_id is
            'file_id после первой успешной отправки атлету. Пусто до неё и после замены.';
        comment on table progress_photo_reminders is
            'Расписание напоминания о фото прогресса. Одна строка на пользователя.';
        comment on table progress_photo_reminder_weekdays is
            'Дни недели напоминания о фото прогресса.';
        """,
    )


def downgrade() -> None:
    op.execute(
        """
        drop table if exists progress_photo_reminder_weekdays cascade;
        drop table if exists progress_photo_reminders cascade;
        drop table if exists progress_photos cascade;
        drop table if exists progress_photo_sets cascade;
        """,
    )
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
