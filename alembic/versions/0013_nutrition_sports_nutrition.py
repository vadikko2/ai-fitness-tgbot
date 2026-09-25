"""Add sports_nutrition text to nutrition recommendations.

Revision ID: 0013_nutrition_sports_nutrition
Revises: 0012_feedback_tickets
Create Date: 2026-09-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_nutrition_sports_nutrition"
down_revision: str | None = "0012_feedback_tickets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        alter table nutrition_recommendations
            add column if not exists sports_nutrition text not null
            default 'Обнови рекомендации по питанию, чтобы получить советы по спортпиту.';
        """,
    )
    op.execute(
        """
        comment on column nutrition_recommendations.sports_nutrition is
            'Текст рекомендаций по спортивному питанию / добавкам.';
        """,
    )


def downgrade() -> None:
    op.execute(
        """
        alter table nutrition_recommendations
            drop column if exists sports_nutrition;
        """,
    )
