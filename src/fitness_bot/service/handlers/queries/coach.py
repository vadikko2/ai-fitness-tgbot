from __future__ import annotations

from datetime import UTC, datetime

import cqrs

from fitness_bot.domain.enums import CoachVerificationStatus, SessionStatus
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import User
from fitness_bot.domain.workout.week_progress import training_week_progress
from fitness_bot.service.authz import require_coach_of, require_moderator, require_verified_coach
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.queries import coach as queries
from fitness_bot.service.ports.object_storage import ObjectStorage

IDLE_DAYS_THRESHOLD = queries.IDLE_DAYS_THRESHOLD


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


async def _count_recent_videos(repos, client_user_id, *, session_limit: int = 20) -> int:
    sessions = await repos.sessions.list_completed_for_user(client_user_id, limit=session_limit)
    total = 0
    for session in sessions:
        videos = await repos.technique_videos.list_for_session(session.id)
        total += len(videos)
    return total


class CountActiveClientsForCoachQueryHandler(
    cqrs.RequestHandler[queries.CountActiveClientsForCoachQuery, queries.CountActiveClientsForCoachQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: queries.CountActiveClientsForCoachQuery,
    ) -> queries.CountActiveClientsForCoachQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            profile = await repos.coaches.get_profile(user.id)
            if profile is None or profile.status != CoachVerificationStatus.VERIFIED:
                return queries.CountActiveClientsForCoachQueryResult(
                    count=0,
                    coach_status=profile.status if profile else None,
                )
            count = await repos.coaches.count_active_clients(user.id)
            return queries.CountActiveClientsForCoachQueryResult(count=count, coach_status=profile.status)


class ListPendingCoachApplicationsQueryHandler(
    cqrs.RequestHandler[
        queries.ListPendingCoachApplicationsQuery,
        queries.ListPendingCoachApplicationsQueryResult,
    ],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: queries.ListPendingCoachApplicationsQuery,
    ) -> queries.ListPendingCoachApplicationsQueryResult:
        async with self._uow.transaction() as repos:
            require_moderator(_require_user(await repos.users.get_by_telegram_id(request.telegram_user_id)))
            apps = await repos.coaches.list_pending_applications(limit=request.limit, offset=request.offset)
            return queries.ListPendingCoachApplicationsQueryResult(
                items=[
                    queries.PendingApplicationItem(
                        application_id=item.id,
                        display_name=item.display_name,
                        bio=item.bio,
                        portfolio_url=item.portfolio_url,
                        created_at=item.created_at,
                    )
                    for item in apps
                ],
            )



class PrepareCoachApplicationCredentialQueryHandler(
    cqrs.RequestHandler[
        queries.PrepareCoachApplicationCredentialQuery,
        queries.PrepareCoachApplicationCredentialQueryResult,
    ],
):
    def __init__(self, uow: IUow, object_storage: ObjectStorage) -> None:
        self._uow = uow
        self._object_storage = object_storage

    async def handle(
        self,
        request: queries.PrepareCoachApplicationCredentialQuery,
    ) -> queries.PrepareCoachApplicationCredentialQueryResult:
        async with self._uow.transaction() as repos:
            require_moderator(_require_user(await repos.users.get_by_telegram_id(request.telegram_user_id)))
            application = await repos.coaches.get_application(request.application_id)
            if application is None:
                raise DomainError("application not found")
            try:
                body = await self._object_storage.get(application.credential_object_key)
            except KeyError:
                return queries.PrepareCoachApplicationCredentialQueryResult(
                    application_id=application.id,
                    display_name=application.display_name,
                    bio=application.bio,
                    portfolio_url=application.portfolio_url,
                    credential_caption=application.credential_caption,
                    missing=True,
                )
            return queries.PrepareCoachApplicationCredentialQueryResult(
                application_id=application.id,
                display_name=application.display_name,
                bio=application.bio,
                portfolio_url=application.portfolio_url,
                credential_caption=application.credential_caption,
                body=body,
                content_type=application.credential_content_type,
            )


class ListMyCoachApplicationsQueryHandler(
    cqrs.RequestHandler[queries.ListMyCoachApplicationsQuery, queries.ListMyCoachApplicationsQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: queries.ListMyCoachApplicationsQuery,
    ) -> queries.ListMyCoachApplicationsQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            apps = await repos.coaches.list_applications_for_user(
                user.id,
                limit=request.limit,
                offset=request.offset,
            )
            return queries.ListMyCoachApplicationsQueryResult(
                items=[
                    queries.MyCoachApplicationItem(
                        application_id=item.id,
                        display_name=item.display_name,
                        status=item.status,
                        created_at=item.created_at,
                        moderator_comment=item.moderator_comment,
                        resolved_at=item.resolved_at,
                    )
                    for item in apps
                ],
            )


class GetMyCoachApplicationQueryHandler(
    cqrs.RequestHandler[queries.GetMyCoachApplicationQuery, queries.GetMyCoachApplicationQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: queries.GetMyCoachApplicationQuery,
    ) -> queries.GetMyCoachApplicationQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            application = await repos.coaches.get_application(request.application_id)
            if application is None or application.user_id != user.id:
                raise DomainError("application not found")
            return queries.GetMyCoachApplicationQueryResult(
                application_id=application.id,
                display_name=application.display_name,
                status=application.status,
                created_at=application.created_at,
                moderator_comment=application.moderator_comment,
                resolved_at=application.resolved_at,
                bio=application.bio,
                portfolio_url=application.portfolio_url,
            )


class ListModeratorsQueryHandler(
    cqrs.RequestHandler[queries.ListModeratorsQuery, queries.ListModeratorsQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.ListModeratorsQuery) -> queries.ListModeratorsQueryResult:
        async with self._uow.transaction() as repos:
            require_moderator(_require_user(await repos.users.get_by_telegram_id(request.telegram_user_id)))
            mods = await repos.users.list_moderators()
            return queries.ListModeratorsQueryResult(
                items=[
                    queries.ModeratorItem(
                        user_id=item.id,
                        telegram_user_id=item.telegram_user_id,
                        display_name=item.display_name,
                        telegram_username=item.telegram_username,
                    )
                    for item in mods
                ],
            )


class SearchCoachesQueryHandler(
    cqrs.RequestHandler[queries.SearchCoachesQuery, queries.SearchCoachesQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.SearchCoachesQuery) -> queries.SearchCoachesQueryResult:
        async with self._uow.transaction() as repos:
            _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            q = (request.q or "").strip()[:80] or None
            profiles = await repos.coaches.search_verified(q=q, limit=request.limit, offset=request.offset)
            items: list[queries.CoachCardItem] = []
            for profile in profiles:
                invite = await repos.coaches.get_active_invite(profile.user_id)
                items.append(
                    queries.CoachCardItem(
                        user_id=profile.user_id,
                        display_name=profile.display_name,
                        bio=profile.bio,
                        rating_avg=profile.rating_avg,
                        rating_count=profile.rating_count,
                        accepting_clients=profile.accepting_clients,
                        invite_code=invite.code if invite and invite.is_active else None,
                    ),
                )
            return queries.SearchCoachesQueryResult(items=items)


class GetCoachPublicCardQueryHandler(
    cqrs.RequestHandler[queries.GetCoachPublicCardQuery, queries.GetCoachPublicCardQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetCoachPublicCardQuery) -> queries.GetCoachPublicCardQueryResult:
        async with self._uow.transaction() as repos:
            viewer = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            profile = await repos.coaches.get_profile(request.coach_user_id)
            if profile is None or profile.status != CoachVerificationStatus.VERIFIED:
                raise DomainError("coach not found")
            invite = await repos.coaches.get_active_invite(profile.user_id)
            review = await repos.coaches.get_review(coach_user_id=profile.user_id, author_user_id=viewer.id)
            return queries.GetCoachPublicCardQueryResult(
                coach_user_id=profile.user_id,
                display_name=profile.display_name,
                bio=profile.bio,
                rating_avg=profile.rating_avg,
                rating_count=profile.rating_count,
                accepting_clients=profile.accepting_clients,
                invite_code=invite.code if invite and invite.is_active and profile.accepting_clients else None,
                my_review_stars=review.stars if review else None,
            )


class ListCoachClientsQueryHandler(
    cqrs.RequestHandler[queries.ListCoachClientsQuery, queries.ListCoachClientsQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.ListCoachClientsQuery) -> queries.ListCoachClientsQueryResult:
        async with self._uow.transaction() as repos:
            coach = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            await require_verified_coach(repos, coach)
            links = await repos.coaches.list_active_clients(coach.id)
            invite = await repos.coaches.get_active_invite(coach.id)
            items: list[queries.CoachClientItem] = []
            for link in links:
                client = await repos.users.get_by_id(link.client_user_id)
                items.append(
                    queries.CoachClientItem(
                        link_id=link.id,
                        client_user_id=link.client_user_id,
                        display_name=client.public_label() if client else f"user_{str(link.client_user_id)[:8]}",
                        telegram_username=client.telegram_username if client else None,
                    ),
                )
            return queries.ListCoachClientsQueryResult(
                items=items,
                invite_code=invite.code if invite and invite.is_active else None,
            )


class GetClientCardQueryHandler(
    cqrs.RequestHandler[queries.GetClientCardQuery, queries.GetClientCardQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetClientCardQuery) -> queries.GetClientCardQueryResult:
        now = request.now or datetime.now(UTC)
        async with self._uow.transaction() as repos:
            coach = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            await require_coach_of(repos, coach, request.client_user_id)
            client = _require_user(await repos.users.get_by_id(request.client_user_id))
            link = await repos.coaches.get_active_link(coach_user_id=coach.id, client_user_id=client.id)
            if link is None:
                raise DomainError("active link not found")
            history = await repos.sessions.list_completed_for_user(client.id, limit=1)
            days_since = None
            if history:
                completed_at = history[0].completed_at or history[0].started_at
                days_since = max(0, (now.astimezone(UTC) - completed_at.astimezone(UTC)).days)
            program = None
            progress = None
            if client.active_program_id is not None:
                program = await repos.programs.get_by_id(client.active_program_id)
                if program is not None:
                    sessions = await repos.sessions.list_completed_for_user(client.id, limit=50)
                    progress = training_week_progress(
                        program,
                        sessions,
                        timezone_offset=client.timezone_offset,
                        now=now,
                    )
            return queries.GetClientCardQueryResult(
                client_user_id=client.id,
                display_name=client.public_label(),
                telegram_username=client.telegram_username,
                timezone_offset=client.timezone_offset,
                days_since_last_completed_session=days_since,
                idle_badge=days_since is not None and days_since >= IDLE_DAYS_THRESHOLD,
                active_program_title=program.display_title() if program else None,
                program_type=program.program_type if program else None,
                week_finished=progress.week_finished if progress else None,
                planned_weekdays=list(progress.planned_weekdays) if progress else [],
                completed_weekdays=list(progress.completed_weekdays) if progress else [],
                link_id=link.id,
                recent_technique_video_count=await _count_recent_videos(repos, client.id),
            )


class GetCoachCabinetQueryHandler(
    cqrs.RequestHandler[queries.GetCoachCabinetQuery, queries.GetCoachCabinetQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetCoachCabinetQuery) -> queries.GetCoachCabinetQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            profile = await repos.coaches.get_profile(user.id)
            if profile is None:
                return queries.GetCoachCabinetQueryResult(
                    verified=False,
                    status=None,
                    active_clients=0,
                    accepting_clients=False,
                )
            invite = await repos.coaches.get_active_invite(user.id) if profile.is_verified else None
            count = await repos.coaches.count_active_clients(user.id) if profile.is_verified else 0
            pending = profile.status == CoachVerificationStatus.PENDING
            return queries.GetCoachCabinetQueryResult(
                verified=profile.is_verified,
                status=profile.status,
                active_clients=count,
                accepting_clients=profile.accepting_clients,
                invite_code=invite.code if invite and invite.is_active else None,
                pending_application=pending,
            )


class ListProgramCatalogQueryHandler(
    cqrs.RequestHandler[queries.ListProgramCatalogQuery, queries.ListProgramCatalogQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.ListProgramCatalogQuery) -> queries.ListProgramCatalogQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            programs = await repos.programs.list_catalog_for_user(
                user.id,
                limit=request.limit,
                offset=request.offset,
            )
            return queries.ListProgramCatalogQueryResult(
                items=[
                    queries.CatalogProgramItem(
                        program_id=item.id,
                        title=item.display_title(),
                        status=item.status.value,
                        distribution_code=item.distribution_code,
                        author_label=item.author_label,
                        source_program_id=item.source_program_id,
                    )
                    for item in programs
                ],
            )


class GetCatalogProgramQueryHandler(
    cqrs.RequestHandler[queries.GetCatalogProgramQuery, queries.GetCatalogProgramQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetCatalogProgramQuery) -> queries.GetCatalogProgramQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            program = await repos.programs.get_by_id(request.program_id)
            if program is None or program.user_id != user.id:
                raise DomainError("program not found")
            return queries.GetCatalogProgramQueryResult(
                program_id=program.id,
                title=program.display_title(),
                status=program.status.value,
                distribution_code=program.distribution_code,
                author_label=program.author_label,
                document=program.to_document(),
                is_author_template=program.source_program_id is None and program.status.value in {"draft", "published"},
            )


# silence unused import for SessionStatus if needed later
_ = SessionStatus
