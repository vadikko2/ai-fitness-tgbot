from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.enums import CoachVerificationStatus
from fitness_bot.domain.errors import DomainError


class CoachProfile(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    user_id: UUID
    display_name: str
    bio: str = ""
    portfolio_url: str | None = None
    status: CoachVerificationStatus = CoachVerificationStatus.NONE
    accepting_clients: bool = True
    rating_avg: Decimal | None = None
    rating_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        display_name: str,
        bio: str = "",
        portfolio_url: str | None = None,
    ) -> CoachProfile:
        name = display_name.strip()
        if not name:
            raise DomainError("display_name is required")
        return cls(
            user_id=user_id,
            display_name=name,
            bio=bio.strip(),
            portfolio_url=(portfolio_url.strip() if portfolio_url else None),
            status=CoachVerificationStatus.NONE,
        )

    def mark_pending(self) -> None:
        self.status = CoachVerificationStatus.PENDING
        self.updated_at = datetime.now(UTC)

    def mark_verified(self) -> None:
        self.status = CoachVerificationStatus.VERIFIED
        self.accepting_clients = True
        self.updated_at = datetime.now(UTC)

    def mark_rejected(self) -> None:
        self.status = CoachVerificationStatus.REJECTED
        self.updated_at = datetime.now(UTC)

    def suspend(self) -> None:
        if self.status != CoachVerificationStatus.VERIFIED:
            raise DomainError("only verified coaches can be suspended")
        self.status = CoachVerificationStatus.SUSPENDED
        self.accepting_clients = False
        self.updated_at = datetime.now(UTC)

    def set_accepting_clients(self, value: bool) -> None:
        if self.status != CoachVerificationStatus.VERIFIED:
            raise DomainError("only verified coaches can toggle accepting_clients")
        self.accepting_clients = value
        self.updated_at = datetime.now(UTC)

    def apply_rating_aggregate(self, *, avg: Decimal | None, count: int) -> None:
        if count < 0:
            raise DomainError("rating_count must be non-negative")
        self.rating_avg = avg
        self.rating_count = count
        self.updated_at = datetime.now(UTC)

    @property
    def is_verified(self) -> bool:
        return self.status == CoachVerificationStatus.VERIFIED
