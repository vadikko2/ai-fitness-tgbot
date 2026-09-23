from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.enums import ExpectedInput, ProfileField
from fitness_bot.presentation.flow_helpers import clear_profile_edit, goal_label, show_next_onboarding_step
from fitness_bot.presentation.keyboards import home_keyboard
from fitness_bot.presentation.routers.coach import render_home
from fitness_bot.service.models.commands.coach import SyncUserIdentityCommand
from fitness_bot.service.models.commands.users import EnsureUserCommand, ExpectInputCommand
from fitness_bot.service.models.queries.users import GetHomeQuery, GetProfileQuery
from fitness_bot.shared.settings import load_settings


def _display_name(user) -> str | None:
    parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(part for part in parts if part).strip()
    return name or None


def create_start_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    start_router = Router(name="start")

    @start_router.message(CommandStart())
    async def handle_start(message: Message) -> None:
        assert message.from_user is not None
        clear_profile_edit(message.from_user.id)
        settings = load_settings()
        payload = (message.text or "").split(maxsplit=1)
        deep_link = payload[1].strip() if len(payload) > 1 else None

        await mediator.send(
            EnsureUserCommand(telegram_user_id=message.from_user.id, chat_id=message.chat.id),
        )
        await mediator.send(
            SyncUserIdentityCommand(
                telegram_user_id=message.from_user.id,
                chat_id=message.chat.id,
                display_name=_display_name(message.from_user),
                telegram_username=message.from_user.username,
                bootstrap_moderator_ids=list(settings.bootstrap_moderator_ids()),
            ),
        )
        profile = await mediator.send(GetProfileQuery(telegram_user_id=message.from_user.id))
        if profile.profile_complete:
            if deep_link:
                # Pending deep-link resume after onboarding is handled elsewhere; store as CODE_OR_LINK.
                await mediator.send(
                    ExpectInputCommand(
                        telegram_user_id=message.from_user.id,
                        expected_input=ExpectedInput.CODE_OR_LINK,
                        expected_field=deep_link,
                    ),
                )
                await message.answer(f"Получена ссылка/код: {deep_link}\nОтправьте его ещё раз или вставьте вручную.")
            home = await mediator.send(GetHomeQuery(telegram_user_id=message.from_user.id))
            greeting = jinja_env.get_template("start.j2").render(profile_complete=True)
            status_line = ""
            if home.show_coach_badge:
                status_line = f"\nСтатус: тренер · подопечных: {home.active_clients_count}"
            elif home.coach_status == "pending":
                status_line = "\nЗаявка на проверке. Обычно 1–2 дня."
            home_text = jinja_env.get_template("home.j2").render(
                age=home.age,
                weight_kg=home.weight_kg,
                goal=home.goal,
                goal_label=goal_label(home.goal),
                coach_status_line=status_line,
            )
            await message.answer(
                f"{greeting}\n\n{home_text}",
                reply_markup=home_keyboard(
                    show_coach_badge=home.show_coach_badge,
                    active_clients_count=home.active_clients_count,
                    is_moderator=home.is_moderator,
                ),
            )
            return
        if deep_link:
            await mediator.send(
                ExpectInputCommand(
                    telegram_user_id=message.from_user.id,
                    expected_input=ExpectedInput.CODE_OR_LINK,
                    expected_field=f"pending:{deep_link}",
                ),
            )
        if profile.next_field == ProfileField.SEX:
            await mediator.send(
                ExpectInputCommand(
                    telegram_user_id=message.from_user.id,
                    expected_input=ExpectedInput.PROFILE_FIELD,
                    expected_field=ProfileField.SEX.value,
                ),
            )
        await show_next_onboarding_step(
            message=message,
            jinja_env=jinja_env,
            mediator=mediator,
            profile=profile,
        )

    return start_router


_ = render_home
