from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fitness_bot.domain.enums import FeedbackKind, FeedbackStatus
from fitness_bot.service.models.queries.base import Query, QueryResult


class ListMyFeedbackQuery(Query):
    telegram_user_id: int
    kind: FeedbackKind
    offset: int = 0
    limit: int = 5


class FeedbackListItem(QueryResult):
    ticket_id: UUID
    status: FeedbackStatus
    body: str
    created_at: datetime


class ListMyFeedbackQueryResult(QueryResult):
    items: list[FeedbackListItem]
    total: int
    offset: int


class GetMyFeedbackQuery(Query):
    telegram_user_id: int
    ticket_id: UUID


class GetMyFeedbackQueryResult(QueryResult):
    ticket_id: UUID
    kind: FeedbackKind
    status: FeedbackStatus
    body: str
    moderator_reply: str | None
    photo_file_ids: list[str]
    created_at: datetime
