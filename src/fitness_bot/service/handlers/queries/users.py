from __future__ import annotations

from datetime import UTC, datetime

import cqrs

from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import User
from fitness_bot.service.handlers.commands.users import parse_pending_site_id
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.queries import users as queries


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


async def _profile_payload(repos, user: User, *, now: datetime) -> queries.GetProfileQueryResult:
    latest = await repos.weights.latest_for_user(user.id)
    has_weight = latest is not None
    next_field = user.next_missing_field(has_weight=has_weight)
    return queries.GetProfileQueryResult(
        user_id=user.id,
        telegram_user_id=user.telegram_user_id,
        chat_id=user.chat_id,
        sex=user.sex,
        birth_year=user.birth_year,
        age=user.age(now=now),
        height_cm=user.height_cm,
        weight_kg=latest.kilograms if latest else None,
        experience=user.experience,
        experience_details=user.experience_details,
        days_per_week=user.days_per_week,
        training_weekdays=sorted(user.training_weekdays),
        equipment=user.equipment,
        limitations=user.limitations,
        activity_level=user.activity_level,
        session_minutes=user.session_minutes,
        body_fat_pct=user.body_fat_pct,
        body_fat_set=user.body_fat_set,
        supplements=sorted(user.supplements) if user.supplements is not None else None,
        supplements_other=user.supplements_other,
        diet_prefs=user.diet_prefs,
        pharma=user.pharma,
        timezone_offset=user.timezone_offset,
        goal=user.goal,
        nutrition_stale=user.nutrition_stale,
        expected_input=user.expected_input,
        expected_field=user.expected_field,
        focus_slot=user.focus_slot,
        profile_complete=user.is_profile_complete(has_weight=has_weight),
        next_field=next_field,
        pending_site_id=parse_pending_site_id(user.expected_field),
    )


class GetProfileQueryHandler(cqrs.RequestHandler[queries.GetProfileQuery, queries.GetProfileQueryResult]):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetProfileQuery) -> queries.GetProfileQueryResult:
        now = request.now or datetime.now(UTC)
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            return await _profile_payload(repos, user, now=now)


class GetHomeQueryHandler(cqrs.RequestHandler[queries.GetHomeQuery, queries.GetHomeQueryResult]):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetHomeQuery) -> queries.GetHomeQueryResult:
        now = request.now or datetime.now(UTC)
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            profile = await _profile_payload(repos, user, now=now)
            coach_profile = await repos.coaches.get_profile(user.id)
            coach_status = coach_profile.status.value if coach_profile else None
            active_clients = 0
            show_badge = False
            if coach_profile is not None and coach_profile.is_verified:
                active_clients = await repos.coaches.count_active_clients(user.id)
                show_badge = True
            return queries.GetHomeQueryResult(
                user_id=profile.user_id,
                profile_complete=profile.profile_complete,
                goal=profile.goal,
                age=profile.age,
                weight_kg=profile.weight_kg,
                is_moderator=user.is_moderator,
                coach_status=coach_status,
                active_clients_count=active_clients,
                show_coach_badge=show_badge,
            )


class GetWorkflowQueryHandler(cqrs.RequestHandler[queries.GetWorkflowQuery, queries.GetWorkflowQueryResult]):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetWorkflowQuery) -> queries.GetWorkflowQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            latest = await repos.weights.latest_for_user(user.id)
            has_weight = latest is not None
            return queries.GetWorkflowQueryResult(
                user_id=user.id,
                chat_id=user.chat_id,
                expected_input=user.expected_input,
                expected_field=user.expected_field,
                focus_slot=user.focus_slot,
                pending_site_id=parse_pending_site_id(user.expected_field),
                profile_complete=user.is_profile_complete(has_weight=has_weight),
                goal=user.goal,
            )
