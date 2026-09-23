from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.enums import CoachNoteVisibility
from fitness_bot.domain.errors import DomainError


class CoachNote(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    coach_user_id: UUID
    client_user_id: UUID
    visibility: CoachNoteVisibility
    body: str
    session_id: UUID | None = None
    slot_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    revoked_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        coach_user_id: UUID,
        client_user_id: UUID,
        visibility: CoachNoteVisibility,
        body: str,
        session_id: UUID | None = None,
        slot_id: UUID | None = None,
    ) -> CoachNote:
        text = body.strip()
        if not text:
            raise DomainError("note body is required")
        if len(text) > 2000:
            raise DomainError("note body must be ≤2000 characters")
        if slot_id is not None and session_id is None:
            raise DomainError("slot_id requires session_id")
        return cls(
            coach_user_id=coach_user_id,
            client_user_id=client_user_id,
            visibility=visibility,
            body=text,
            session_id=session_id,
            slot_id=slot_id,
        )

    def revoke(self, *, now: datetime | None = None) -> None:
        if self.revoked_at is not None:
            return
        self.revoked_at = now or datetime.now(UTC)
        self.updated_at = self.revoked_at
