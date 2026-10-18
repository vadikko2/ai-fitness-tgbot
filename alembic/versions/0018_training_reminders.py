"""Training-day reminder prefs and last-sent dates.

Revision ID: 0018_training_reminders
Revises: 0017_wellbeing_tracking
Create Date: 2026-10-18

Evening 20:00 and morning 09:00 are fixed in code (no time columns).
Existing users are inserted with both nudges on.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018_training_reminders"
down_revision: str | None = "0017_wellbeing_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists training_reminders (
            user_id uuid primary key references users(id) on delete cascade,
            evening_enabled boolean not null default true,
            morning_enabled boolean not null default true,
            last_evening_sent_on date null,
            last_morning_sent_on date null
        );
        """,
    )
    op.execute(
        """
        comment on table training_reminders is
            'Вечер 20:00 про завтра и утро 09:00 про сегодня. Время фиксировано, last_* — не слать дважды за сутки.';
        """,
    )
    op.execute(
        """
        insert into training_reminders (user_id)
        select id from users
        on conflict (user_id) do nothing;
        """,
    )


def downgrade() -> None:
    op.execute("drop table if exists training_reminders;")
