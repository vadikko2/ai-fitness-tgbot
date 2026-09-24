from __future__ import annotations

from uuid import UUID

import cqrs

from fitness_bot.domain.enums import FeedbackStatus
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.feedback.ticket import (
    MAX_FEEDBACK_PHOTO_BYTES,
    FeedbackModeratorMessage,
    FeedbackTicket,
    feedback_photo_object_key,
)
from fitness_bot.domain.users.user import User
from fitness_bot.service.authz import require_moderator
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.commands import feedback as cmds
from fitness_bot.service.ports.object_storage import ObjectStorage


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


class StartFeedbackDraftCommandHandler(
    cqrs.RequestHandler[cmds.StartFeedbackDraftCommand, cmds.StartFeedbackDraftCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.StartFeedbackDraftCommand) -> cmds.StartFeedbackDraftCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if request.body.strip():
                ticket = FeedbackTicket.start(author_user_id=user.id, kind=request.kind, body=request.body)
            else:
                ticket = FeedbackTicket.begin(author_user_id=user.id, kind=request.kind)
            saved = await repos.feedback.add(ticket)
            return cmds.StartFeedbackDraftCommandResult(ticket_id=saved.id, kind=saved.kind)


class SetFeedbackBodyCommandHandler(
    cqrs.RequestHandler[cmds.SetFeedbackBodyCommand, cmds.SetFeedbackBodyCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.SetFeedbackBodyCommand) -> cmds.SetFeedbackBodyCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            ticket = await _own_ticket(repos, user_id=user.id, ticket_id=request.ticket_id)
            ticket.set_body(request.body)
            saved = await repos.feedback.save(ticket)
            return cmds.SetFeedbackBodyCommandResult(ticket_id=saved.id, kind=saved.kind)


class AttachFeedbackPhotoCommandHandler(
    cqrs.RequestHandler[cmds.AttachFeedbackPhotoCommand, cmds.AttachFeedbackPhotoCommandResult],
):
    def __init__(self, uow: IUow, object_storage: ObjectStorage) -> None:
        self._uow = uow
        self._object_storage = object_storage

    async def handle(self, request: cmds.AttachFeedbackPhotoCommand) -> cmds.AttachFeedbackPhotoCommandResult:
        content_type = (request.content_type or "").strip().lower()
        if not content_type.startswith("image/"):
            raise DomainError("feedback photo must be an image")
        byte_size = len(request.body)
        if byte_size <= 0 or byte_size > MAX_FEEDBACK_PHOTO_BYTES:
            raise DomainError("feedback photo size must be between 1 and 10 MiB")
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            ticket = await _own_ticket(repos, user_id=user.id, ticket_id=request.ticket_id)
            object_key = feedback_photo_object_key(
                kind=ticket.kind,
                author_user_id=user.id,
                ticket_id=ticket.id,
                index=len(ticket.photos) + 1,
                content_type=content_type,
            )
            await self._object_storage.put(object_key, request.body, content_type)
            ticket.attach_photo(object_key=object_key, content_type=content_type, file_id=request.file_id)
            saved = await repos.feedback.save(ticket)
            return cmds.AttachFeedbackPhotoCommandResult(ticket_id=saved.id, photo_count=len(saved.photos))


class SubmitFeedbackCommandHandler(
    cqrs.RequestHandler[cmds.SubmitFeedbackCommand, cmds.SubmitFeedbackCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.SubmitFeedbackCommand) -> cmds.SubmitFeedbackCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            ticket = await _own_ticket(repos, user_id=user.id, ticket_id=request.ticket_id)
            ticket.submit()
            saved = await repos.feedback.save(ticket)
            moderators = await repos.users.list_moderators()
            return cmds.SubmitFeedbackCommandResult(
                ticket_id=saved.id,
                kind=saved.kind,
                body=saved.body,
                photo_file_ids=list(saved.photo_file_ids),
                author_display_name=user.display_name or user.telegram_username,
                moderator_chats=[{"user_id": str(item.id), "chat_id": item.chat_id} for item in moderators],
            )


class RecordFeedbackModeratorMessageCommandHandler(
    cqrs.RequestHandler[
        cmds.RecordFeedbackModeratorMessageCommand,
        cmds.RecordFeedbackModeratorMessageCommandResult,
    ],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.RecordFeedbackModeratorMessageCommand,
    ) -> cmds.RecordFeedbackModeratorMessageCommandResult:
        async with self._uow.transaction() as repos:
            message = FeedbackModeratorMessage(
                ticket_id=request.ticket_id,
                moderator_user_id=request.moderator_user_id,
                chat_id=request.chat_id,
                message_id=request.message_id,
            )
            saved = await repos.feedback.add_moderator_message(message)
            return cmds.RecordFeedbackModeratorMessageCommandResult(message_id=saved.message_id)


class ChangeFeedbackStatusCommandHandler(
    cqrs.RequestHandler[cmds.ChangeFeedbackStatusCommand, cmds.ChangeFeedbackStatusCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.ChangeFeedbackStatusCommand) -> cmds.ChangeFeedbackStatusCommandResult:
        async with self._uow.transaction() as repos:
            actor = require_moderator(_require_user(await repos.users.get_by_telegram_id(request.telegram_user_id)))
            ticket = await repos.feedback.get(request.ticket_id)
            if ticket is None or ticket.status == FeedbackStatus.DRAFT:
                raise DomainError("feedback not found")
            if request.status == FeedbackStatus.IN_PROGRESS:
                ticket.take_in_progress(moderator_user_id=actor.id)
            elif request.status == FeedbackStatus.RESOLVED:
                ticket.resolve(moderator_user_id=actor.id)
            elif request.status == FeedbackStatus.CANCELLED:
                ticket.cancel(moderator_user_id=actor.id, reply=request.reply or "")
            else:
                raise DomainError("status cannot change")
            saved = await repos.feedback.save(ticket)
            author = await repos.users.get_by_id(saved.author_user_id)
            refs = await repos.feedback.list_moderator_messages(saved.id)
            return cmds.ChangeFeedbackStatusCommandResult(
                ticket_id=saved.id,
                kind=saved.kind,
                status=saved.status,
                body=saved.body,
                moderator_reply=saved.moderator_reply,
                author_chat_id=author.chat_id if author else None,
                author_display_name=(author.display_name or author.telegram_username) if author else None,
                moderator_message_refs=[
                    {"chat_id": item.chat_id, "message_id": item.message_id} for item in refs
                ],
            )


async def _own_ticket(repos, *, user_id: UUID, ticket_id: UUID) -> FeedbackTicket:
    ticket = await repos.feedback.get(ticket_id)
    if ticket is None or ticket.author_user_id != user_id:
        raise DomainError("feedback not found")
    return ticket
