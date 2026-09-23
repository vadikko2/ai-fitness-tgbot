from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.enums import CoachLinkStatus
from fitness_bot.domain.errors import DomainError


class CoachClientLink(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    coach_user_id: UUID
    client_user_id: UUID
    status: CoachLinkStatus = CoachLinkStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    activated_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by_user_id: UUID | None = None

    @classmethod
    def activate(
        cls,
        *,
        coach_user_id: UUID,
        client_user_id: UUID,
        now: datetime | None = None,
    ) -> CoachClientLink:
        if coach_user_id == client_user_id:
            raise DomainError("cannot link to yourself")
        moment = now or datetime.now(UTC)
        return cls(
            coach_user_id=coach_user_id,
            client_user_id=client_user_id,
            status=CoachLinkStatus.ACTIVE,
            created_at=moment,
            activated_at=moment,
        )

    def revoke(self, *, actor_user_id: UUID, now: datetime | None = None) -> None:
        if self.status == CoachLinkStatus.REVOKED:
            raise DomainError("link already revoked")
        if actor_user_id not in {self.coach_user_id, self.client_user_id}:
            raise DomainError("only coach or client can unlink")
        moment = now or datetime.now(UTC)
        self.status = CoachLinkStatus.REVOKED
        self.revoked_at = moment
        self.revoked_by_user_id = actor_user_id

    @property
    def is_active(self) -> bool:
        return self.status == CoachLinkStatus.ACTIVE
