from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.enums import FeedbackKind, FeedbackStatus
from fitness_bot.domain.errors import DomainError

MAX_FEEDBACK_BODY = 2000
MAX_FEEDBACK_PHOTOS = 3
MAX_FEEDBACK_PHOTO_BYTES = 10 * 1024 * 1024
FEEDBACK_PAGE_SIZE = 5
IDEA_PHOTO_PREFIX = "ideas"
PROBLEM_PHOTO_PREFIX = "problems"

_OPEN_STATUSES = frozenset({FeedbackStatus.NEW, FeedbackStatus.IN_PROGRESS})


class FeedbackPhoto(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    object_key: str
    content_type: str
    file_id: str


def feedback_photo_object_key(
    *,
    kind: FeedbackKind,
    author_user_id: UUID,
    ticket_id: UUID,
    index: int,
    content_type: str,
) -> str:
    folder = IDEA_PHOTO_PREFIX if kind == FeedbackKind.IDEA else PROBLEM_PHOTO_PREFIX
    normalized = content_type.lower()
    if "png" in normalized:
        extension = "png"
    elif "webp" in normalized:
        extension = "webp"
    elif "gif" in normalized:
        extension = "gif"
    else:
        extension = "jpg"
    return f"{folder}/{author_user_id}/{ticket_id}/{index}.{extension}"


class FeedbackTicket(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    author_user_id: UUID
    kind: FeedbackKind
    body: str
    status: FeedbackStatus = FeedbackStatus.DRAFT
    moderator_reply: str | None = None
    resolved_by_user_id: UUID | None = None
    photos: list[FeedbackPhoto] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None

    @classmethod
    def begin(cls, *, author_user_id: UUID, kind: FeedbackKind) -> FeedbackTicket:
        return cls(author_user_id=author_user_id, kind=kind, body="")

    @classmethod
    def start(cls, *, author_user_id: UUID, kind: FeedbackKind, body: str) -> FeedbackTicket:
        ticket = cls.begin(author_user_id=author_user_id, kind=kind)
        ticket.set_body(body)
        return ticket

    def set_body(self, body: str) -> None:
        if self.status != FeedbackStatus.DRAFT:
            raise DomainError("already sent")
        text = body.strip()
        if not text:
            raise DomainError("text is required")
        if len(text) > MAX_FEEDBACK_BODY:
            raise DomainError("text must be ≤2000 characters")
        self.body = text
        self.updated_at = datetime.now(UTC)

    def attach_photo(self, *, object_key: str, content_type: str, file_id: str) -> None:
        key = object_key.strip()
        token = file_id.strip()
        mime = content_type.strip().lower()
        if not key:
            raise DomainError("photo is required")
        if not token:
            raise DomainError("photo is required")
        if not mime.startswith("image/"):
            raise DomainError("feedback photo must be an image")
        if self.status != FeedbackStatus.DRAFT:
            raise DomainError("photos can be attached only before sending")
        if len(self.photos) >= MAX_FEEDBACK_PHOTOS:
            raise DomainError("at most 3 photos")
        expected_prefix = IDEA_PHOTO_PREFIX if self.kind == FeedbackKind.IDEA else PROBLEM_PHOTO_PREFIX
        if not key.startswith(f"{expected_prefix}/"):
            raise DomainError("photo folder does not match feedback kind")
        self.photos = [*self.photos, FeedbackPhoto(object_key=key, content_type=mime, file_id=token)]
        self.updated_at = datetime.now(UTC)

    @property
    def photo_file_ids(self) -> list[str]:
        return [photo.file_id for photo in self.photos]

    def submit(self, *, now: datetime | None = None) -> None:
        if self.status != FeedbackStatus.DRAFT:
            raise DomainError("already sent")
        if not self.body.strip():
            raise DomainError("text is required")
        moment = now or datetime.now(UTC)
        self.status = FeedbackStatus.NEW
        self.updated_at = moment

    def take_in_progress(self, *, moderator_user_id: UUID, now: datetime | None = None) -> None:
        if self.status == FeedbackStatus.IN_PROGRESS:
            raise DomainError("already in this status")
        if self.status != FeedbackStatus.NEW:
            raise DomainError("status cannot change")
        moment = now or datetime.now(UTC)
        self.status = FeedbackStatus.IN_PROGRESS
        self.resolved_by_user_id = moderator_user_id
        self.updated_at = moment

    def resolve(self, *, moderator_user_id: UUID, now: datetime | None = None) -> None:
        if self.status not in _OPEN_STATUSES:
            raise DomainError("status cannot change")
        moment = now or datetime.now(UTC)
        self.status = FeedbackStatus.RESOLVED
        self.resolved_by_user_id = moderator_user_id
        self.resolved_at = moment
        self.updated_at = moment

    def cancel(self, *, moderator_user_id: UUID, reply: str, now: datetime | None = None) -> None:
        if self.status not in _OPEN_STATUSES:
            raise DomainError("status cannot change")
        text = reply.strip()
        if not text:
            raise DomainError("cancel reply is required")
        if len(text) > MAX_FEEDBACK_BODY:
            raise DomainError("reply must be ≤2000 characters")
        moment = now or datetime.now(UTC)
        self.status = FeedbackStatus.CANCELLED
        self.moderator_reply = text
        self.resolved_by_user_id = moderator_user_id
        self.resolved_at = moment
        self.updated_at = moment


class FeedbackModeratorMessage(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    ticket_id: UUID
    moderator_user_id: UUID
    chat_id: int
    message_id: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
