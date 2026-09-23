from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fitness_bot.domain.errors import DomainError

MAX_TECHNIQUE_VIDEO_BYTES = 20 * 1024 * 1024


def technique_video_object_key(*, user_id: UUID, session_id: UUID, slot_id: UUID) -> str:
    return f"users/{user_id}/sessions/{session_id}/slots/{slot_id}"


class TechniqueVideo(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    slot_id: UUID
    user_id: UUID
    session_id: UUID
    object_key: str
    content_type: str
    byte_size: int
    telegram_file_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _invariants(self) -> TechniqueVideo:
        if not self.content_type.startswith("video/"):
            raise DomainError("technique video content_type must start with video/")
        if self.byte_size <= 0 or self.byte_size > MAX_TECHNIQUE_VIDEO_BYTES:
            raise DomainError("technique video size must be between 1 and 20 MiB")
        expected = technique_video_object_key(
            user_id=self.user_id,
            session_id=self.session_id,
            slot_id=self.slot_id,
        )
        if self.object_key != expected:
            raise DomainError("technique video object_key does not match slot path")
        return self

    @classmethod
    def create(
        cls,
        *,
        slot_id: UUID,
        user_id: UUID,
        session_id: UUID,
        content_type: str,
        byte_size: int,
        now: datetime | None = None,
    ) -> TechniqueVideo:
        return cls(
            slot_id=slot_id,
            user_id=user_id,
            session_id=session_id,
            object_key=technique_video_object_key(
                user_id=user_id,
                session_id=session_id,
                slot_id=slot_id,
            ),
            content_type=content_type,
            byte_size=byte_size,
            telegram_file_id=None,
            created_at=now or datetime.now(UTC),
        )

    def replace_file(self, *, content_type: str, byte_size: int, now: datetime | None = None) -> TechniqueVideo:
        return self.model_copy(
            update={
                "content_type": content_type,
                "byte_size": byte_size,
                "telegram_file_id": None,
                "created_at": now or datetime.now(UTC),
            },
        )

    def remember_telegram_file_id(self, file_id: str) -> TechniqueVideo:
        if not file_id.strip():
            raise DomainError("telegram_file_id must not be empty")
        return self.model_copy(update={"telegram_file_id": file_id})
