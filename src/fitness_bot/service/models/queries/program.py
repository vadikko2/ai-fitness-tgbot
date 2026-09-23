from __future__ import annotations

from uuid import UUID

from fitness_bot.domain.enums import ProgramStatus, ProgramType, ProposalKind, ProposalStatus
from fitness_bot.domain.workout.document import WorkoutDocument
from fitness_bot.service.models.queries.base import Query, QueryResult


class GetActiveProgramQuery(Query):
    telegram_user_id: int


class GetActiveProgramQueryResult(QueryResult):
    program_id: UUID | None = None
    program_type: ProgramType | None = None
    status: ProgramStatus | None = None
    document: WorkoutDocument | None = None


class GetPendingProposalQuery(Query):
    telegram_user_id: int


class GetPendingProposalQueryResult(QueryResult):
    proposal_id: UUID | None = None
    kind: ProposalKind | None = None
    status: ProposalStatus | None = None
    program_type: ProgramType | None = None
    reply: str = ""
    document: WorkoutDocument | None = None
    has_document: bool = False
