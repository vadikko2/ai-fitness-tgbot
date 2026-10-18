from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.errors import DomainError

# Unapplied notes older than this no longer feed generations automatically.
WELLBEING_FRESHNESS_WINDOW = timedelta(hours=48)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


class WellbeingEntry(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    text: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    applied_at: datetime | None = None
    proposal_id: UUID | None = None

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

    def is_fresh(self, *, now: datetime, max_age: timedelta = WELLBEING_FRESHNESS_WINDOW) -> bool:
        return _aware(now) - _aware(self.created_at) <= max_age


def fresh_unapplied(
    entries: Iterable[WellbeingEntry],
    *,
    now: datetime,
    max_age: timedelta = WELLBEING_FRESHNESS_WINDOW,
) -> list[WellbeingEntry]:
    return [entry for entry in entries if not entry.is_applied and entry.is_fresh(now=now, max_age=max_age)]
