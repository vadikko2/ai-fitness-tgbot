from __future__ import annotations

import cqrs

from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import User
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.queries import program as queries


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


class GetActiveProgramQueryHandler(
    cqrs.RequestHandler[queries.GetActiveProgramQuery, queries.GetActiveProgramQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetActiveProgramQuery) -> queries.GetActiveProgramQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_program_id is None:
                return queries.GetActiveProgramQueryResult()
            program = await repos.programs.get_by_id(user.active_program_id)
            if program is None:
                return queries.GetActiveProgramQueryResult()
            return queries.GetActiveProgramQueryResult(
                program_id=program.id,
                program_type=program.program_type,
                status=program.status,
                document=program.to_document(),
            )


class GetPendingProposalQueryHandler(
    cqrs.RequestHandler[queries.GetPendingProposalQuery, queries.GetPendingProposalQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetPendingProposalQuery) -> queries.GetPendingProposalQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            pending = await repos.proposals.get_pending_for_user(user.id)
            if pending is None:
                return queries.GetPendingProposalQueryResult()
            return queries.GetPendingProposalQueryResult(
                proposal_id=pending.id,
                kind=pending.kind,
                status=pending.status,
                program_type=pending.program_type,
                reply=pending.reply,
                document=pending.document,
                has_document=pending.document is not None,
            )
