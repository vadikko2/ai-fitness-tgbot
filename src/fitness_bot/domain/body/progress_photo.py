from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fitness_bot.domain.enums import ProgressPhotoAngle
from fitness_bot.domain.errors import DomainError

MAX_PROGRESS_PHOTO_BYTES = 10 * 1024 * 1024
PROGRESS_PHOTO_ANGLE_ORDER: tuple[ProgressPhotoAngle, ...] = (
    ProgressPhotoAngle.FRONT,
    ProgressPhotoAngle.SIDE,
    ProgressPhotoAngle.BACK,
)


def progress_photo_object_key(*, user_id: UUID, set_id: UUID, angle: ProgressPhotoAngle) -> str:
    return f"users/{user_id}/progress_photos/{set_id}/{angle.value}.jpg"


class ProgressPhoto(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    set_id: UUID
    angle: ProgressPhotoAngle
    object_key: str
    content_type: str
    byte_size: int
    telegram_file_id: str | None = None

    @model_validator(mode="after")
    def _invariants(self) -> ProgressPhoto:
        if not self.content_type.startswith("image/"):
            raise DomainError("progress photo content_type must start with image/")
        if self.byte_size <= 0 or self.byte_size > MAX_PROGRESS_PHOTO_BYTES:
            raise DomainError("progress photo size must be between 1 and 10 MiB")
        return self

    @classmethod
    def create(
        cls,
        *,
        set_id: UUID,
        user_id: UUID,
        angle: ProgressPhotoAngle,
        content_type: str,
        byte_size: int,
        photo_id: UUID | None = None,
    ) -> ProgressPhoto:
        photo_id = photo_id or uuid4()
        return cls(
            id=photo_id,
            set_id=set_id,
            angle=angle,
            object_key=progress_photo_object_key(user_id=user_id, set_id=set_id, angle=angle),
            content_type=content_type,
            byte_size=byte_size,
            telegram_file_id=None,
        )

    def replace_file(self, *, content_type: str, byte_size: int) -> ProgressPhoto:
        return self.model_copy(
            update={
                "content_type": content_type,
                "byte_size": byte_size,
                "telegram_file_id": None,
            },
        )

    def remember_telegram_file_id(self, file_id: str) -> ProgressPhoto:
        if not file_id.strip():
            raise DomainError("telegram_file_id must not be empty")
        return self.model_copy(update={"telegram_file_id": file_id})


class ProgressPhotoSet(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    local_date: date
    complete: bool = False
    photos: list[ProgressPhoto] = Field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        local_date: date,
        captured_at: datetime | None = None,
        set_id: UUID | None = None,
    ) -> ProgressPhotoSet:
        return cls(
            id=set_id or uuid4(),
            user_id=user_id,
            local_date=local_date,
            captured_at=captured_at or datetime.now(UTC),
            complete=False,
            photos=[],
        )

    def photo_for(self, angle: ProgressPhotoAngle) -> ProgressPhoto | None:
        for photo in self.photos:
            if photo.angle == angle:
                return photo
        return None

    def next_angle(self) -> ProgressPhotoAngle | None:
        present = {photo.angle for photo in self.photos}
        for angle in PROGRESS_PHOTO_ANGLE_ORDER:
            if angle not in present:
                return angle
        return None

    def upsert_photo(
        self,
        *,
        angle: ProgressPhotoAngle,
        content_type: str,
        byte_size: int,
        now: datetime | None = None,
    ) -> tuple[ProgressPhoto, bool]:
        """Add or replace a photo for ``angle``. Returns (photo, replaced)."""
        existing = self.photo_for(angle)
        if existing is not None:
            photo = existing.replace_file(content_type=content_type, byte_size=byte_size)
            self.photos = [photo if item.id == existing.id else item for item in self.photos]
            replaced = True
        else:
            photo = ProgressPhoto.create(
                set_id=self.id,
                user_id=self.user_id,
                angle=angle,
                content_type=content_type,
                byte_size=byte_size,
            )
            self.photos = [*self.photos, photo]
            replaced = False
        self.captured_at = now or datetime.now(UTC)
        self.complete = self.next_angle() is None
        return photo, replaced

    def remember_file_id(self, *, photo_id: UUID, telegram_file_id: str) -> ProgressPhoto:
        for index, photo in enumerate(self.photos):
            if photo.id == photo_id:
                updated = photo.remember_telegram_file_id(telegram_file_id)
                self.photos = [updated if item.id == photo_id else item for item in self.photos]
                return updated
        raise DomainError("progress photo not found")
