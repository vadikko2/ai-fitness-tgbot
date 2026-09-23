"""Add profile MVP fields: activity, session length, body fat, supplements, diet, experience level, pharma.

Revision ID: 0008_profile_fields_mvp
Revises: 0007_expected_input_slot_load
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_profile_fields_mvp"
down_revision: str | None = "0007_expected_input_slot_load"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        alter table users
            add column if not exists experience_details text,
            add column if not exists activity_level text
                check (
                    activity_level is null
                    or activity_level in ('sedentary', 'light', 'moderate', 'high')
                ),
            add column if not exists session_minutes smallint
                check (
                    session_minutes is null
                    or session_minutes in (30, 45, 60, 90)
                ),
            add column if not exists body_fat_pct numeric(4, 1)
                check (body_fat_pct is null or (body_fat_pct > 0 and body_fat_pct < 100)),
            add column if not exists body_fat_set boolean not null default false,
            add column if not exists supplements text,
            add column if not exists supplements_other text,
            add column if not exists diet_prefs text,
            add column if not exists pharma text;
        """,
    )
    # Move free-text experience that is not an enum value into experience_details.
    op.execute(
        """
        update users
        set
            experience_details = coalesce(experience_details, experience),
            experience = null
        where experience is not null
          and experience not in ('beginner', 'intermediate', 'advanced');
        """,
    )
    op.execute(
        """
        alter table users drop constraint if exists users_experience_level_check;
        alter table users
            add constraint users_experience_level_check check (
                experience is null
                or experience in ('beginner', 'intermediate', 'advanced')
            );
        """,
    )
    op.execute(
        """
        comment on column users.experience is
            'Уровень опыта: beginner / intermediate / advanced.';
        comment on column users.experience_details is
            'Опциональные детали опыта свободным текстом.';
        comment on column users.activity_level is
            'Бытовая активность вне зала: sedentary / light / moderate / high.';
        comment on column users.session_minutes is
            'Целевая длительность тренировки в минутах: 30 / 45 / 60 / 90.';
        comment on column users.body_fat_pct is
            'Процент жира, если пользователь указал число.';
        comment on column users.body_fat_set is
            'true, если шаг % жира пройден (число или «не знаю»).';
        comment on column users.supplements is
            'JSON-массив кодов спортпита (none/protein/creatine/...).';
        comment on column users.supplements_other is
            'Текст для supplements=other.';
        comment on column users.diet_prefs is
            'Пищевые предпочтения и ограничения свободным текстом.';
        comment on column users.pharma is
            'Опционально: ПЭД/фарма (только редактирование профиля). Пустая строка = не принимаю.';
        """,
    )


def downgrade() -> None:
    op.execute("alter table users drop constraint if exists users_experience_level_check")
    op.execute(
        """
        alter table users
            drop column if exists experience_details,
            drop column if exists activity_level,
            drop column if exists session_minutes,
            drop column if exists body_fat_pct,
            drop column if exists body_fat_set,
            drop column if exists supplements,
            drop column if exists supplements_other,
            drop column if exists diet_prefs,
            drop column if exists pharma;
        """,
    )
    op.execute(
        """
        comment on column users.experience is 'Свободный текст об опыте тренировок.';
        """,
    )
