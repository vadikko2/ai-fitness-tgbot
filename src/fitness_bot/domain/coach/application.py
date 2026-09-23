from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.enums import CoachApplicationStatus
from fitness_bot.domain.errors import DomainError


class CoachApplication(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    display_name: str
    bio: str
    portfolio_url: str
    credential_object_key: str
    credential_content_type: str
    credential_byte_size: int
    credential_caption: str | None = None
    status: CoachApplicationStatus = CoachApplicationStatus.PENDING
    moderator_comment: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolved_by_user_id: UUID | None = None

    @classmethod
    def submit(
        cls,
        *,
        user_id: UUID,
        display_name: str,
        bio: str,
        portfolio_url: str,
        credential_object_key: str,
        credential_content_type: str,
        credential_byte_size: int,
        credential_caption: str | None = None,
    ) -> CoachApplication:
        name = display_name.strip()
        bio_text = bio.strip()
        url = portfolio_url.strip()
        key = credential_object_key.strip()
        if not name:
            raise DomainError("display_name is required")
        if not bio_text:
            raise DomainError("bio is required")
        if not url:
            raise DomainError("portfolio_url is required")
        if not key:
            raise DomainError("credential file is required")
        if credential_byte_size <= 0:
            raise DomainError("credential_byte_size must be positive")
        return cls(
            user_id=user_id,
            display_name=name,
            bio=bio_text,
            portfolio_url=url,
            credential_object_key=key,
            credential_content_type=credential_content_type.strip() or "application/octet-stream",
            credential_byte_size=credential_byte_size,
            credential_caption=(credential_caption.strip() if credential_caption else None),
        )

    def approve(self, *, moderator_user_id: UUID, now: datetime | None = None) -> None:
        if self.status != CoachApplicationStatus.PENDING:
            raise DomainError("application already processed")
        moment = now or datetime.now(UTC)
        self.status = CoachApplicationStatus.APPROVED
        self.resolved_at = moment
        self.resolved_by_user_id = moderator_user_id
        self.moderator_comment = None

    def reject(self, *, moderator_user_id: UUID, comment: str, now: datetime | None = None) -> None:
        if self.status != CoachApplicationStatus.PENDING:
            raise DomainError("application already processed")
        text = comment.strip()
        if not text:
            raise DomainError("reject comment is required")
        moment = now or datetime.now(UTC)
        self.status = CoachApplicationStatus.REJECTED
        self.resolved_at = moment
        self.resolved_by_user_id = moderator_user_id
        self.moderator_comment = text


class CoachApplicationModeratorMessage(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    application_id: UUID
    moderator_user_id: UUID
    chat_id: int
    message_id: int
    media_message_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
