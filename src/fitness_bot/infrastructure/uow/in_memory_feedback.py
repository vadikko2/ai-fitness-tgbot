from __future__ import annotations

from copy import deepcopy
from uuid import UUID

from fitness_bot.domain.enums import FeedbackKind, FeedbackStatus
from fitness_bot.domain.feedback.ticket import FeedbackModeratorMessage, FeedbackTicket
from fitness_bot.service.interfaces.uow import IFeedbackRepository


class InMemoryFeedbackRepository(IFeedbackRepository):
    def __init__(self) -> None:
        self._tickets: dict[UUID, FeedbackTicket] = {}
        self._messages: dict[UUID, FeedbackModeratorMessage] = {}

    async def add(self, ticket: FeedbackTicket) -> FeedbackTicket:
        stored = deepcopy(ticket)
        self._tickets[stored.id] = stored
        return deepcopy(stored)

    async def get(self, ticket_id: UUID) -> FeedbackTicket | None:
        ticket = self._tickets.get(ticket_id)
        return deepcopy(ticket) if ticket else None

    async def save(self, ticket: FeedbackTicket) -> FeedbackTicket:
        if ticket.id not in self._tickets:
            raise KeyError(ticket.id)
        stored = deepcopy(ticket)
        self._tickets[stored.id] = stored
        return deepcopy(stored)

    async def list_for_author(
        self,
        author_user_id: UUID,
        kind: FeedbackKind,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[FeedbackTicket], int]:
        matched = [
            ticket
            for ticket in self._tickets.values()
            if ticket.author_user_id == author_user_id
            and ticket.kind == kind
            and ticket.status != FeedbackStatus.DRAFT
        ]
        matched.sort(key=lambda item: item.created_at, reverse=True)
        page = matched[offset : offset + limit]
        return [deepcopy(item) for item in page], len(matched)

    async def add_moderator_message(self, message: FeedbackModeratorMessage) -> FeedbackModeratorMessage:
        stored = deepcopy(message)
        self._messages[stored.id] = stored
        return deepcopy(stored)

    async def list_moderator_messages(self, ticket_id: UUID) -> list[FeedbackModeratorMessage]:
        return [deepcopy(item) for item in self._messages.values() if item.ticket_id == ticket_id]
