from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fitness_bot.domain.enums import FeedbackKind, FeedbackStatus
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.feedback.ticket import FeedbackTicket
from fitness_bot.infrastructure.adapters.object_storage import InMemoryObjectStorage
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.authz import AuthorizationError
from fitness_bot.service.handlers.commands.feedback import (
    AttachFeedbackPhotoCommandHandler,
    ChangeFeedbackStatusCommandHandler,
    SetFeedbackBodyCommandHandler,
    StartFeedbackDraftCommandHandler,
    SubmitFeedbackCommandHandler,
)
from fitness_bot.service.handlers.queries.feedback import GetMyFeedbackQueryHandler, ListMyFeedbackQueryHandler
from fitness_bot.service.models.commands.feedback import (
    AttachFeedbackPhotoCommand,
    ChangeFeedbackStatusCommand,
    SetFeedbackBodyCommand,
    StartFeedbackDraftCommand,
    SubmitFeedbackCommand,
)
from fitness_bot.service.models.queries.feedback import GetMyFeedbackQuery, ListMyFeedbackQuery


async def _user(uow: InMemoryUow, telegram_user_id: int, *, moderator: bool = False) -> None:
    async with uow.transaction() as repos:
        user, _ = await repos.users.ensure(telegram_user_id=telegram_user_id, chat_id=telegram_user_id)
        if moderator:
            user.is_moderator = True
            await repos.users.save(user)


async def test_draft_is_hidden_until_submit_and_kinds_stay_separate() -> None:
    uow = InMemoryUow()
    await _user(uow, 1)
    await _user(uow, 2, moderator=True)
    draft = await StartFeedbackDraftCommandHandler(uow).handle(
        StartFeedbackDraftCommand(telegram_user_id=1, kind=FeedbackKind.IDEA, body="хочу тёмную тему"),
    )
    listed = await ListMyFeedbackQueryHandler(uow).handle(
        ListMyFeedbackQuery(telegram_user_id=1, kind=FeedbackKind.IDEA),
    )
    assert listed.total == 0

    storage = InMemoryObjectStorage()
    await AttachFeedbackPhotoCommandHandler(uow, storage).handle(
        AttachFeedbackPhotoCommand(
            telegram_user_id=1,
            ticket_id=draft.ticket_id,
            file_id="photo-1",
            body=b"jpeg-bytes",
            content_type="image/jpeg",
        ),
    )
    stored_keys = list(storage._objects)
    assert len(stored_keys) == 1
    assert stored_keys[0].startswith("ideas/")
    submitted = await SubmitFeedbackCommandHandler(uow).handle(
        SubmitFeedbackCommand(telegram_user_id=1, ticket_id=draft.ticket_id),
    )
    assert submitted.photo_file_ids == ["photo-1"]
    assert submitted.moderator_chats == [{"user_id": submitted.moderator_chats[0]["user_id"], "chat_id": 2}]

    ideas = await ListMyFeedbackQueryHandler(uow).handle(
        ListMyFeedbackQuery(telegram_user_id=1, kind=FeedbackKind.IDEA),
    )
    problems = await ListMyFeedbackQueryHandler(uow).handle(
        ListMyFeedbackQuery(telegram_user_id=1, kind=FeedbackKind.PROBLEM),
    )
    assert ideas.total == 1
    assert ideas.items[0].status == FeedbackStatus.NEW
    assert problems.total == 0

    with pytest.raises(DomainError, match="feedback not found"):
        await GetMyFeedbackQueryHandler(uow).handle(
            GetMyFeedbackQuery(telegram_user_id=2, ticket_id=draft.ticket_id),
        )


async def test_list_pages_five_newest_first() -> None:
    uow = InMemoryUow()
    await _user(uow, 7)
    async with uow.transaction() as repos:
        author = await repos.users.get_by_telegram_id(7)
        assert author is not None
        base = datetime(2026, 9, 1, tzinfo=UTC)
        for index in range(6):
            ticket = FeedbackTicket.start(author_user_id=author.id, kind=FeedbackKind.PROBLEM, body=f"проблема {index}")
            ticket.submit()
            ticket.created_at = base + timedelta(minutes=index)
            await repos.feedback.add(ticket)

    first = await ListMyFeedbackQueryHandler(uow).handle(
        ListMyFeedbackQuery(telegram_user_id=7, kind=FeedbackKind.PROBLEM, offset=0, limit=50),
    )
    second = await ListMyFeedbackQueryHandler(uow).handle(
        ListMyFeedbackQuery(telegram_user_id=7, kind=FeedbackKind.PROBLEM, offset=5),
    )
    assert first.total == 6
    assert len(first.items) == 5
    assert first.items[0].body == "проблема 5"
    assert len(second.items) == 1
    assert second.items[0].body == "проблема 0"


async def test_voice_text_can_arrive_after_a_photo_in_the_same_draft() -> None:
    uow = InMemoryUow()
    await _user(uow, 3)
    draft = await StartFeedbackDraftCommandHandler(uow).handle(
        StartFeedbackDraftCommand(telegram_user_id=3, kind=FeedbackKind.PROBLEM, body=""),
    )
    storage = InMemoryObjectStorage()
    await AttachFeedbackPhotoCommandHandler(uow, storage).handle(
        AttachFeedbackPhotoCommand(
            telegram_user_id=3,
            ticket_id=draft.ticket_id,
            file_id="shot",
            body=b"jpeg-bytes",
            content_type="image/jpeg",
        ),
    )
    with pytest.raises(DomainError, match="text is required"):
        await SubmitFeedbackCommandHandler(uow).handle(
            SubmitFeedbackCommand(telegram_user_id=3, ticket_id=draft.ticket_id),
        )
    updated = await SetFeedbackBodyCommandHandler(uow).handle(
        SetFeedbackBodyCommand(
            telegram_user_id=3,
            ticket_id=draft.ticket_id,
            body="кнопка не нажимается",
        ),
    )
    submitted = await SubmitFeedbackCommandHandler(uow).handle(
        SubmitFeedbackCommand(telegram_user_id=3, ticket_id=updated.ticket_id),
    )
    assert submitted.body == "кнопка не нажимается"
    assert submitted.photo_file_ids == ["shot"]


async def test_moderator_status_flow_notifies_author_chat() -> None:
    uow = InMemoryUow()
    await _user(uow, 10)
    await _user(uow, 11, moderator=True)
    draft = await StartFeedbackDraftCommandHandler(uow).handle(
        StartFeedbackDraftCommand(telegram_user_id=10, kind=FeedbackKind.IDEA, body="добавьте экспорт"),
    )
    await SubmitFeedbackCommandHandler(uow).handle(
        SubmitFeedbackCommand(telegram_user_id=10, ticket_id=draft.ticket_id),
    )

    with pytest.raises(AuthorizationError):
        await ChangeFeedbackStatusCommandHandler(uow).handle(
            ChangeFeedbackStatusCommand(
                telegram_user_id=10,
                ticket_id=draft.ticket_id,
                status=FeedbackStatus.RESOLVED,
            ),
        )

    progressed = await ChangeFeedbackStatusCommandHandler(uow).handle(
        ChangeFeedbackStatusCommand(
            telegram_user_id=11,
            ticket_id=draft.ticket_id,
            status=FeedbackStatus.IN_PROGRESS,
        ),
    )
    assert progressed.status == FeedbackStatus.IN_PROGRESS
    assert progressed.author_chat_id == 10

    cancelled = await ChangeFeedbackStatusCommandHandler(uow).handle(
        ChangeFeedbackStatusCommand(
            telegram_user_id=11,
            ticket_id=draft.ticket_id,
            status=FeedbackStatus.CANCELLED,
            reply="сделаем позже",
        ),
    )
    assert cancelled.status == FeedbackStatus.CANCELLED
    assert cancelled.moderator_reply == "сделаем позже"

    opened = await GetMyFeedbackQueryHandler(uow).handle(
        GetMyFeedbackQuery(telegram_user_id=10, ticket_id=draft.ticket_id),
    )
    assert opened.moderator_reply == "сделаем позже"
    assert opened.status == FeedbackStatus.CANCELLED
