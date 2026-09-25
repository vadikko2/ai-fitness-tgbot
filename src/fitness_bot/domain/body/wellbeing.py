from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.errors import DomainError


class WellbeingEntry(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    text: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    applied_at: datetime | None = None

    @classmethod
    def create(cls, *, user_id: UUID, text: str, now: datetime | None = None) -> WellbeingEntry:
        cleaned = text.strip()
        if not cleaned:
            raise DomainError("wellbeing text must not be empty")
        moment = now or datetime.now(UTC)
        return cls(user_id=user_id, text=cleaned, created_at=moment)

    def mark_applied(self, *, now: datetime | None = None) -> None:
        self.applied_at = now or datetime.now(UTC)

    @property
    def is_applied(self) -> bool:
        return self.applied_at is not None
