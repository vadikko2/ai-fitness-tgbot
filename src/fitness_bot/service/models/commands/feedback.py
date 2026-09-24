from __future__ import annotations

from uuid import UUID

from fitness_bot.domain.enums import FeedbackKind, FeedbackStatus
from fitness_bot.service.models.commands.base import Command, CommandResult


class StartFeedbackDraftCommand(Command):
    telegram_user_id: int
    kind: FeedbackKind
    body: str


class StartFeedbackDraftCommandResult(CommandResult):
    ticket_id: UUID
    kind: FeedbackKind


class SetFeedbackBodyCommand(Command):
    telegram_user_id: int
    ticket_id: UUID
    body: str


class SetFeedbackBodyCommandResult(CommandResult):
    ticket_id: UUID
    kind: FeedbackKind


class AttachFeedbackPhotoCommand(Command):
    telegram_user_id: int
    ticket_id: UUID
    file_id: str
    body: bytes
    content_type: str


class AttachFeedbackPhotoCommandResult(CommandResult):
    ticket_id: UUID
    photo_count: int


class SubmitFeedbackCommand(Command):
    telegram_user_id: int
    ticket_id: UUID


class SubmitFeedbackCommandResult(CommandResult):
    ticket_id: UUID
    kind: FeedbackKind
    body: str
    photo_file_ids: list[str] = []
    author_display_name: str | None = None
    moderator_chats: list[dict] = []


class RecordFeedbackModeratorMessageCommand(Command):
    ticket_id: UUID
    moderator_user_id: UUID
    chat_id: int
    message_id: int


class RecordFeedbackModeratorMessageCommandResult(CommandResult):
    message_id: int


class ChangeFeedbackStatusCommand(Command):
    telegram_user_id: int
    ticket_id: UUID
    status: FeedbackStatus
    reply: str | None = None


class ChangeFeedbackStatusCommandResult(CommandResult):
    ticket_id: UUID
    kind: FeedbackKind
    status: FeedbackStatus
    body: str
    moderator_reply: str | None = None
    author_chat_id: int | None = None
    author_display_name: str | None = None
    moderator_message_refs: list[dict] = []
