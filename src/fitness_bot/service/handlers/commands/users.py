from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import cqrs

from fitness_bot.domain.body.reminder import ProgressPhotoReminder, WeightReminder
from fitness_bot.domain.enums import ExpectedInput, ProfileField
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import User
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.commands import users as cmds


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


class EnsureUserCommandHandler(cqrs.RequestHandler[cmds.EnsureUserCommand, cmds.EnsureUserCommandResult]):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.EnsureUserCommand) -> cmds.EnsureUserCommandResult:
        async with self._uow.transaction() as repos:
            user, created = await repos.users.ensure(
                telegram_user_id=request.telegram_user_id,
                chat_id=request.chat_id,
            )
            if created:
                existing_weight = await repos.weight_reminders.get(user.id)
                if existing_weight is None:
                    await repos.weight_reminders.save(WeightReminder.default_for_user(user_id=user.id))
                existing_photo = await repos.progress_photo_reminders.get(user.id)
                if existing_photo is None:
                    await repos.progress_photo_reminders.save(
                        ProgressPhotoReminder.default_for_user(user_id=user.id),
                    )
            return cmds.EnsureUserCommandResult(user_id=user.id, created=created)


class UpdateProfileCommandHandler(cqrs.RequestHandler[cmds.UpdateProfileCommand, cmds.UpdateProfileCommandResult]):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.UpdateProfileCommand) -> cmds.UpdateProfileCommandResult:
        now = request.now or datetime.now(UTC)
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if request.field == ProfileField.WEIGHT:
                raise DomainError("use RecordWeightCommand for weight")
            user.apply_profile_field(request.field, request.value, now=now)
            latest = await repos.weights.latest_for_user(user.id)
            has_weight = latest is not None
            next_field = user.next_missing_field(has_weight=has_weight)
            if next_field is not None:
                user.expect_input(ExpectedInput.PROFILE_FIELD, expected_field=next_field.value)
            elif user.goal is None:
                user.clear_expectation()
            else:
                user.clear_expectation()
            await repos.users.save(user)
            return cmds.UpdateProfileCommandResult(
                user_id=user.id,
                next_field=next_field,
                profile_complete=user.is_profile_complete(has_weight=has_weight),
            )


class SetGoalCommandHandler(cqrs.RequestHandler[cmds.SetGoalCommand, cmds.SetGoalCommandResult]):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.SetGoalCommand) -> cmds.SetGoalCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            user.set_goal(request.goal)
            await repos.nutrition.mark_all_stale_for_user(user.id)
            latest = await repos.weights.latest_for_user(user.id)
            has_weight = latest is not None
            if user.is_profile_complete(has_weight=has_weight):
                user.clear_expectation()
            await repos.users.save(user)
            return cmds.SetGoalCommandResult(
                user_id=user.id,
                goal=user.goal,
                nutrition_stale=user.nutrition_stale,
            )


class ExpectInputCommandHandler(cqrs.RequestHandler[cmds.ExpectInputCommand, cmds.ExpectInputCommandResult]):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.ExpectInputCommand) -> cmds.ExpectInputCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            expected_field = request.expected_field
            if request.pending_site_id is not None:
                expected_field = str(request.pending_site_id)
            user.expect_input(
                request.expected_input,
                expected_field=expected_field,
                focus_slot=request.focus_slot,
            )
            await repos.users.save(user)
            return cmds.ExpectInputCommandResult(
                user_id=user.id,
                expected_input=user.expected_input,
                expected_field=user.expected_field,
            )


def parse_pending_site_id(expected_field: str | None) -> UUID | None:
    if not expected_field:
        return None
    try:
        return UUID(expected_field)
    except ValueError:
        return None
