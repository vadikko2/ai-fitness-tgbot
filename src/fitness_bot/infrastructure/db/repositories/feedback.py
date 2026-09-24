from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fitness_bot.domain.enums import FeedbackKind, FeedbackStatus
from fitness_bot.domain.feedback.ticket import FeedbackModeratorMessage, FeedbackTicket
from fitness_bot.infrastructure.db.mappers_feedback import (
    apply_feedback_ticket_to_row,
    feedback_message_to_domain,
    feedback_ticket_to_domain,
)
from fitness_bot.infrastructure.db.models import FeedbackModeratorMessageRow, FeedbackTicketRow
from fitness_bot.service.interfaces.uow import IFeedbackRepository


class SqlAlchemyFeedbackRepository(IFeedbackRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, ticket: FeedbackTicket) -> FeedbackTicket:
        row = FeedbackTicketRow(
            id=ticket.id,
            author_user_id=ticket.author_user_id,
            kind=ticket.kind.value,
            body=ticket.body,
        )
        apply_feedback_ticket_to_row(row, ticket)
        self._session.add(row)
        await self._session.flush()
        return feedback_ticket_to_domain(row)

    async def get(self, ticket_id: UUID) -> FeedbackTicket | None:
        row = await self._session.get(FeedbackTicketRow, ticket_id)
        return feedback_ticket_to_domain(row) if row else None

    async def save(self, ticket: FeedbackTicket) -> FeedbackTicket:
        row = await self._session.get(FeedbackTicketRow, ticket.id)
        if row is None:
            raise KeyError(ticket.id)
        apply_feedback_ticket_to_row(row, ticket)
        await self._session.flush()
        return feedback_ticket_to_domain(row)

    async def list_for_author(
        self,
        author_user_id: UUID,
        kind: FeedbackKind,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[FeedbackTicket], int]:
        filters = (
            FeedbackTicketRow.author_user_id == author_user_id,
            FeedbackTicketRow.kind == kind.value,
            FeedbackTicketRow.status != FeedbackStatus.DRAFT.value,
        )
        total = await self._session.scalar(select(func.count()).select_from(FeedbackTicketRow).where(*filters))
        stmt = (
            select(FeedbackTicketRow)
            .where(*filters)
            .order_by(FeedbackTicketRow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [feedback_ticket_to_domain(row) for row in rows], int(total or 0)

    async def add_moderator_message(self, message: FeedbackModeratorMessage) -> FeedbackModeratorMessage:
        row = FeedbackModeratorMessageRow(
            id=message.id,
            ticket_id=message.ticket_id,
            moderator_user_id=message.moderator_user_id,
            chat_id=message.chat_id,
            message_id=message.message_id,
            created_at=message.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return feedback_message_to_domain(row)

    async def list_moderator_messages(self, ticket_id: UUID) -> list[FeedbackModeratorMessage]:
        stmt = select(FeedbackModeratorMessageRow).where(FeedbackModeratorMessageRow.ticket_id == ticket_id)
        rows = (await self._session.scalars(stmt)).all()
        return [feedback_message_to_domain(row) for row in rows]
