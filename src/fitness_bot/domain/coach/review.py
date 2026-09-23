from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fitness_bot.domain.errors import DomainError


class CoachReview(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    coach_user_id: UUID
    author_user_id: UUID
    stars: int
    body: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("stars")
    @classmethod
    def _validate_stars(cls, value: int) -> int:
        if value < 1 or value > 5:
            raise DomainError("stars must be between 1 and 5")
        return value

    @classmethod
    def create(
        cls,
        *,
        coach_user_id: UUID,
        author_user_id: UUID,
        stars: int,
        body: str | None = None,
    ) -> CoachReview:
        if coach_user_id == author_user_id:
            raise DomainError("cannot review yourself")
        text = body.strip() if body else None
        if text is not None and len(text) > 1000:
            raise DomainError("review body must be ≤1000 characters")
        return cls(
            coach_user_id=coach_user_id,
            author_user_id=author_user_id,
            stars=stars,
            body=text or None,
        )

    def update(self, *, stars: int, body: str | None = None) -> None:
        if stars < 1 or stars > 5:
            raise DomainError("stars must be between 1 and 5")
        text = body.strip() if body else None
        if text is not None and len(text) > 1000:
            raise DomainError("review body must be ≤1000 characters")
        self.stars = stars
        self.body = text or None
        self.updated_at = datetime.now(UTC)
