from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fitness_bot.domain.enums import CoachApplicationStatus, CoachVerificationStatus, ProgramType
from fitness_bot.domain.workout.document import WorkoutDocument
from fitness_bot.service.models.queries.base import Query, QueryResult

IDLE_DAYS_THRESHOLD = 3


class CountActiveClientsForCoachQuery(Query):
    telegram_user_id: int


class CountActiveClientsForCoachQueryResult(QueryResult):
    count: int
    coach_status: CoachVerificationStatus | None = None


class ListPendingCoachApplicationsQuery(Query):
    telegram_user_id: int
    limit: int = 20
    offset: int = 0


class PendingApplicationItem(QueryResult):
    application_id: UUID
    display_name: str
    bio: str
    portfolio_url: str
    created_at: datetime


class ListPendingCoachApplicationsQueryResult(QueryResult):
    items: list[PendingApplicationItem]


class PrepareCoachApplicationCredentialQuery(Query):
    telegram_user_id: int
    application_id: UUID


class PrepareCoachApplicationCredentialQueryResult(QueryResult):
    application_id: UUID
    display_name: str
    bio: str
    portfolio_url: str
    credential_caption: str | None = None
    body: bytes | None = None
    content_type: str | None = None
    missing: bool = False


class ListMyCoachApplicationsQuery(Query):
    telegram_user_id: int
    limit: int = 20
    offset: int = 0


class MyCoachApplicationItem(QueryResult):
    application_id: UUID
    display_name: str
    status: CoachApplicationStatus
    created_at: datetime
    moderator_comment: str | None = None
    resolved_at: datetime | None = None


class ListMyCoachApplicationsQueryResult(QueryResult):
    items: list[MyCoachApplicationItem]


class GetMyCoachApplicationQuery(Query):
    telegram_user_id: int
    application_id: UUID


class GetMyCoachApplicationQueryResult(QueryResult):
    application_id: UUID
    display_name: str
    status: CoachApplicationStatus
    created_at: datetime
    moderator_comment: str | None = None
    resolved_at: datetime | None = None
    bio: str
    portfolio_url: str


class ListModeratorsQuery(Query):
    telegram_user_id: int


class ModeratorItem(QueryResult):
    user_id: UUID
    telegram_user_id: int
    display_name: str | None
    telegram_username: str | None


class ListModeratorsQueryResult(QueryResult):
    items: list[ModeratorItem]


class SearchCoachesQuery(Query):
    telegram_user_id: int
    q: str | None = None
    limit: int = 10
    offset: int = 0


class CoachCardItem(QueryResult):
    user_id: UUID
    display_name: str
    bio: str
    rating_avg: Decimal | None
    rating_count: int
    accepting_clients: bool
    invite_code: str | None = None


class SearchCoachesQueryResult(QueryResult):
    items: list[CoachCardItem]


class GetCoachPublicCardQuery(Query):
    telegram_user_id: int
    coach_user_id: UUID


class GetCoachPublicCardQueryResult(QueryResult):
    coach_user_id: UUID
    display_name: str
    bio: str
    rating_avg: Decimal | None
    rating_count: int
    accepting_clients: bool
    invite_code: str | None = None
    my_review_stars: int | None = None


class ListCoachClientsQuery(Query):
    telegram_user_id: int


class CoachClientItem(QueryResult):
    link_id: UUID
    client_user_id: UUID
    display_name: str
    telegram_username: str | None = None


class ListCoachClientsQueryResult(QueryResult):
    items: list[CoachClientItem]
    invite_code: str | None = None


class GetClientCardQuery(Query):
    telegram_user_id: int
    client_user_id: UUID
    now: datetime | None = None


class GetClientCardQueryResult(QueryResult):
    client_user_id: UUID
    display_name: str
    telegram_username: str | None
    timezone_offset: str | None
    days_since_last_completed_session: int | None
    idle_badge: bool
    active_program_title: str | None
    program_type: ProgramType | None
    week_finished: bool | None = None
    planned_weekdays: list[int] = []
    completed_weekdays: list[int] = []
    link_id: UUID
    recent_technique_video_count: int = 0


class GetCoachCabinetQuery(Query):
    telegram_user_id: int


class GetCoachCabinetQueryResult(QueryResult):
    verified: bool
    status: CoachVerificationStatus | None
    active_clients: int
    accepting_clients: bool
    invite_code: str | None = None
    pending_application: bool = False
    display_name: str | None = None


class ListProgramCatalogQuery(Query):
    telegram_user_id: int
    limit: int = 20
    offset: int = 0


class CatalogProgramItem(QueryResult):
    program_id: UUID
    title: str
    status: str
    distribution_code: str | None = None
    author_label: str | None = None
    source_program_id: UUID | None = None


class ListProgramCatalogQueryResult(QueryResult):
    items: list[CatalogProgramItem]


class GetCatalogProgramQuery(Query):
    telegram_user_id: int
    program_id: UUID


class GetCatalogProgramQueryResult(QueryResult):
    program_id: UUID
    title: str
    status: str
    distribution_code: str | None
    author_label: str | None
    document: WorkoutDocument
    is_author_template: bool
    source_program_id: UUID | None = None


class GetMyCoachQuery(Query):
    telegram_user_id: int


class GetMyCoachQueryResult(QueryResult):
    linked: bool
    coach_user_id: UUID | None = None
    display_name: str | None = None
    bio: str | None = None
    rating_avg: Decimal | None = None
    rating_count: int = 0
    accepting_clients: bool = False
