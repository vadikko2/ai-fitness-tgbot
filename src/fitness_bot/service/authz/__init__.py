from __future__ import annotations

from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import User
from fitness_bot.service.interfaces.uow import IUowRepositories


class AuthorizationError(DomainError):
    """Actor is not allowed to perform the requested action."""


def require_moderator(actor: User) -> User:
    if not actor.is_moderator:
        raise AuthorizationError("moderator role required")
    return actor


async def require_verified_coach(repos: IUowRepositories, actor: User):
    profile = await repos.coaches.get_profile(actor.id)
    if profile is None or not profile.is_verified:
        raise AuthorizationError("verified coach required")
    return profile


async def require_coach_of(repos: IUowRepositories, actor: User, client_user_id) -> None:
    await require_verified_coach(repos, actor)
    link = await repos.coaches.get_active_link(coach_user_id=actor.id, client_user_id=client_user_id)
    if link is None:
        raise AuthorizationError("active coach-client link required")
