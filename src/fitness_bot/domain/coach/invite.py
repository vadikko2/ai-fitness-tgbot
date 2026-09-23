from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.errors import DomainError

_CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_invite_code(*, length: int = 8) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


class CoachInvite(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    code: str
    coach_user_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    revoked_at: datetime | None = None
    uses_count: int = 0
    max_uses: int | None = None
    expires_at: datetime | None = None

    @classmethod
    def create(cls, *, coach_user_id: UUID, code: str | None = None) -> CoachInvite:
        value = (code or generate_invite_code()).strip().upper()
        if len(value) < 4:
            raise DomainError("invite code too short")
        return cls(code=value, coach_user_id=coach_user_id)

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= datetime.now(UTC):
            return False
        if self.max_uses is not None and self.uses_count >= self.max_uses:
            return False
        return True

    def revoke(self, *, now: datetime | None = None) -> None:
        if self.revoked_at is not None:
            return
        self.revoked_at = now or datetime.now(UTC)

    def record_use(self) -> None:
        if not self.is_active:
            raise DomainError("invite is not active")
        self.uses_count += 1
