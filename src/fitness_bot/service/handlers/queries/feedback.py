from __future__ import annotations

import cqrs

from fitness_bot.domain.enums import FeedbackStatus
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.feedback.ticket import FEEDBACK_PAGE_SIZE
from fitness_bot.domain.users.user import User
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.queries import feedback as queries


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


class ListMyFeedbackQueryHandler(
    cqrs.RequestHandler[queries.ListMyFeedbackQuery, queries.ListMyFeedbackQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.ListMyFeedbackQuery) -> queries.ListMyFeedbackQueryResult:
        limit = request.limit if 0 < request.limit <= FEEDBACK_PAGE_SIZE else FEEDBACK_PAGE_SIZE
        offset = max(request.offset, 0)
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            tickets, total = await repos.feedback.list_for_author(
                user.id,
                request.kind,
                limit=limit,
                offset=offset,
            )
            return queries.ListMyFeedbackQueryResult(
                items=[
                    queries.FeedbackListItem(
                        ticket_id=item.id,
                        status=item.status,
                        body=item.body,
                        created_at=item.created_at,
                    )
                    for item in tickets
                ],
                total=total,
                offset=offset,
            )


class GetMyFeedbackQueryHandler(
    cqrs.RequestHandler[queries.GetMyFeedbackQuery, queries.GetMyFeedbackQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetMyFeedbackQuery) -> queries.GetMyFeedbackQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            ticket = await repos.feedback.get(request.ticket_id)
            if ticket is None or ticket.author_user_id != user.id or ticket.status == FeedbackStatus.DRAFT:
                raise DomainError("feedback not found")
            return queries.GetMyFeedbackQueryResult(
                ticket_id=ticket.id,
                kind=ticket.kind,
                status=ticket.status,
                body=ticket.body,
                moderator_reply=ticket.moderator_reply,
                photo_file_ids=list(ticket.photo_file_ids),
                created_at=ticket.created_at,
            )
