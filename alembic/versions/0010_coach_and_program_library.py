"""Coach mode foundation: moderators, coach tables, program library fields.

Revision ID: 0010_coach_and_program_library
Revises: 0009_expand_goal_values
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_coach_and_program_library"
down_revision: str | None = "0009_expand_goal_values"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        alter table users
            add column if not exists display_name text,
            add column if not exists telegram_username text,
            add column if not exists is_moderator boolean not null default false;
        """,
    )
    op.execute(
        """
        create index if not exists ix_users_moderators
            on users (id)
            where is_moderator;
        """,
    )
    op.execute(
        """
        comment on column users.display_name is 'Telegram full_name snapshot for roster/search.';
        comment on column users.telegram_username is 'Telegram username without @.';
        comment on column users.is_moderator is 'Moderator ACL for coach applications.';
        """,
    )

    op.execute("alter table programs drop constraint if exists programs_status_check;")
    op.execute(
        """
        alter table programs
            add constraint programs_status_check
            check (status in ('draft', 'published', 'active', 'archived'));
        """,
    )
    op.execute(
        """
        alter table programs
            add column if not exists title text,
            add column if not exists distribution_code text,
            add column if not exists published_at timestamptz,
            add column if not exists source_program_id uuid references programs (id),
            add column if not exists source_author_user_id uuid references users (id),
            add column if not exists assigned_by_user_id uuid references users (id),
            add column if not exists author_label text;
        """,
    )
    op.execute(
        """
        create unique index if not exists uq_programs_distribution_code
            on programs (distribution_code)
            where distribution_code is not null;
        """,
    )
    op.execute(
        """
        create index if not exists ix_programs_user_catalog
            on programs (user_id, status, created_at desc);
        """,
    )
    op.execute(
        """
        comment on column programs.status is
            'draft | published | active | archived. Library cards are draft/published; week plan is active.';
        comment on column programs.title is 'Human title for library and push notifications.';
        comment on column programs.distribution_code is 'Short claim code for published author programs.';
        comment on column programs.source_program_id is 'Original published program when claimed.';
        comment on column programs.assigned_by_user_id is 'Coach who assigned this active plan, if any.';
        """,
    )

    op.execute(
        """
        create table if not exists coach_profiles (
            user_id uuid primary key references users (id) on delete cascade,
            display_name text not null,
            bio text not null default '',
            portfolio_url text,
            status text not null default 'none'
                check (status in ('none', 'pending', 'verified', 'rejected', 'suspended')),
            accepting_clients boolean not null default true,
            rating_avg numeric(3, 2),
            rating_count integer not null default 0,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        );
        """,
    )
    op.execute(
        """
        create index if not exists ix_coach_profiles_search
            on coach_profiles (status, accepting_clients, rating_avg desc nulls last, rating_count desc);
        """,
    )

    op.execute(
        """
        create table if not exists coach_applications (
            id uuid primary key default gen_random_uuid(),
            user_id uuid not null references users (id) on delete cascade,
            display_name text not null,
            bio text not null,
            portfolio_url text not null,
            credential_object_key text not null,
            credential_content_type text not null,
            credential_byte_size integer not null,
            credential_caption text,
            status text not null default 'pending'
                check (status in ('pending', 'approved', 'rejected')),
            moderator_comment text,
            created_at timestamptz not null default now(),
            resolved_at timestamptz,
            resolved_by_user_id uuid references users (id)
        );
        """,
    )
    op.execute(
        """
        create index if not exists ix_coach_applications_pending
            on coach_applications (created_at)
            where status = 'pending';
        """,
    )

    op.execute(
        """
        create table if not exists coach_application_moderator_messages (
            id uuid primary key default gen_random_uuid(),
            application_id uuid not null references coach_applications (id) on delete cascade,
            moderator_user_id uuid not null references users (id) on delete cascade,
            chat_id bigint not null,
            message_id integer not null,
            media_message_id integer,
            created_at timestamptz not null default now(),
            unique (application_id, moderator_user_id)
        );
        """,
    )

    op.execute(
        """
        create table if not exists coach_invites (
            id uuid primary key default gen_random_uuid(),
            code text not null unique,
            coach_user_id uuid not null references users (id) on delete cascade,
            created_at timestamptz not null default now(),
            revoked_at timestamptz,
            uses_count integer not null default 0,
            max_uses integer,
            expires_at timestamptz
        );
        """,
    )
    op.execute(
        """
        create unique index if not exists uq_coach_invites_one_active
            on coach_invites (coach_user_id)
            where revoked_at is null;
        """,
    )

    op.execute(
        """
        create table if not exists coach_client_links (
            id uuid primary key default gen_random_uuid(),
            coach_user_id uuid not null references users (id) on delete cascade,
            client_user_id uuid not null references users (id) on delete cascade,
            status text not null default 'active'
                check (status in ('pending', 'active', 'revoked')),
            created_at timestamptz not null default now(),
            activated_at timestamptz,
            revoked_at timestamptz,
            revoked_by_user_id uuid references users (id),
            check (coach_user_id <> client_user_id)
        );
        """,
    )
    op.execute(
        """
        create unique index if not exists uq_coach_client_links_active_pair
            on coach_client_links (coach_user_id, client_user_id)
            where status in ('pending', 'active');
        """,
    )
    op.execute(
        """
        create unique index if not exists uq_coach_client_links_one_active_coach
            on coach_client_links (client_user_id)
            where status = 'active';
        """,
    )
    op.execute(
        """
        create index if not exists ix_coach_client_links_coach_active
            on coach_client_links (coach_user_id)
            where status = 'active';
        """,
    )

    op.execute(
        """
        create table if not exists coach_reviews (
            id uuid primary key default gen_random_uuid(),
            coach_user_id uuid not null references users (id) on delete cascade,
            author_user_id uuid not null references users (id) on delete cascade,
            stars smallint not null check (stars between 1 and 5),
            body text,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            unique (coach_user_id, author_user_id),
            check (coach_user_id <> author_user_id)
        );
        """,
    )

    op.execute(
        """
        create table if not exists coach_reports (
            id uuid primary key default gen_random_uuid(),
            reporter_user_id uuid not null references users (id) on delete cascade,
            coach_user_id uuid not null references users (id) on delete cascade,
            body text not null,
            status text not null default 'open' check (status in ('open', 'resolved')),
            created_at timestamptz not null default now(),
            resolved_at timestamptz,
            check (reporter_user_id <> coach_user_id)
        );
        """,
    )
    op.execute(
        """
        create unique index if not exists uq_coach_reports_one_open
            on coach_reports (reporter_user_id, coach_user_id)
            where status = 'open';
        """,
    )

    op.execute(
        """
        create table if not exists coach_notes (
            id uuid primary key default gen_random_uuid(),
            coach_user_id uuid not null references users (id) on delete cascade,
            client_user_id uuid not null references users (id) on delete cascade,
            visibility text not null check (visibility in ('private', 'shared')),
            body text not null,
            session_id uuid references sessions (id) on delete set null,
            slot_id uuid references exercise_slots (id) on delete set null,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            revoked_at timestamptz
        );
        """,
    )
    op.execute(
        """
        create index if not exists ix_coach_notes_client_shared
            on coach_notes (client_user_id, created_at desc)
            where visibility = 'shared' and revoked_at is null;
        """,
    )


def downgrade() -> None:
    op.execute("drop table if exists coach_notes cascade;")
    op.execute("drop table if exists coach_reports cascade;")
    op.execute("drop table if exists coach_reviews cascade;")
    op.execute("drop table if exists coach_client_links cascade;")
    op.execute("drop table if exists coach_invites cascade;")
    op.execute("drop table if exists coach_application_moderator_messages cascade;")
    op.execute("drop table if exists coach_applications cascade;")
    op.execute("drop table if exists coach_profiles cascade;")
    op.execute("drop index if exists ix_programs_user_catalog;")
    op.execute("drop index if exists uq_programs_distribution_code;")
    op.execute(
        """
        alter table programs
            drop column if exists title,
            drop column if exists distribution_code,
            drop column if exists published_at,
            drop column if exists source_program_id,
            drop column if exists source_author_user_id,
            drop column if exists assigned_by_user_id,
            drop column if exists author_label;
        """,
    )
    op.execute("alter table programs drop constraint if exists programs_status_check;")
    op.execute(
        """
        alter table programs
            add constraint programs_status_check
            check (status in ('active', 'archived'));
        """,
    )
    op.execute("drop index if exists ix_users_moderators;")
    op.execute(
        """
        alter table users
            drop column if exists display_name,
            drop column if exists telegram_username,
            drop column if exists is_moderator;
        """,
    )
