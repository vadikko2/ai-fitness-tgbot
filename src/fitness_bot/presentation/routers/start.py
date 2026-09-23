from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.enums import ExpectedInput, ProfileField
from fitness_bot.presentation.flow_helpers import (
    clear_profile_edit,
    home_keyboard_from,
    render_home_text,
    show_next_onboarding_step,
)
from fitness_bot.presentation.routers.coach import (
    _invite_token_from_start_payload,
    _is_own_invite_code,
    render_home,
)
from fitness_bot.service.models.commands.coach import SyncUserIdentityCommand
from fitness_bot.service.models.commands.users import EnsureUserCommand, ExpectInputCommand
from fitness_bot.service.models.queries.coach import GetCoachCabinetQuery
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
        invite_share = _invite_token_from_start_payload(deep_link) if deep_link else None

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
            if invite_share:
                cab = await mediator.send(
                    GetCoachCabinetQuery(telegram_user_id=message.from_user.id),
                )
                own_invite = _is_own_invite_code(
                    raw_or_share=invite_share,
                    cabinet_invite_code=cab.invite_code,
                )
                await mediator.send(
                    ExpectInputCommand(
                        telegram_user_id=message.from_user.id,
                        expected_input=ExpectedInput.NONE,
                    ),
                )
                if own_invite:
                    await message.answer("Это ваш код приглашения, отправьте его клиенту.")
                else:
                    # Confirm before linking — same as manual «Ввести код»; no re-onboarding.
                    raw_code = invite_share[2:] if invite_share.casefold().startswith("c_") else invite_share
                    kb = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="Продолжить — дать доступ",
                                    callback_data=f"coach_accept:{raw_code}",
                                ),
                            ],
                            [InlineKeyboardButton(text="Отмена", callback_data="home")],
                        ],
                    )
                    await message.answer(
                        "Это код тренера. Он увидит прогресс, замеры и видео техники. Подключить?",
                        reply_markup=kb,
                    )
            elif deep_link:
                # Non-invite deep link (e.g. program): keep paste-resume path.
                await mediator.send(
                    ExpectInputCommand(
                        telegram_user_id=message.from_user.id,
                        expected_input=ExpectedInput.CODE_OR_LINK,
                        expected_field=deep_link,
                    ),
                )
                await message.answer(
                    f"Получена ссылка/код: {deep_link}\nОтправьте его ещё раз или вставьте вручную.",
                )
            home = await mediator.send(GetHomeQuery(telegram_user_id=message.from_user.id))
            greeting = jinja_env.get_template("start.j2").render(profile_complete=True)
            home_text = render_home_text(jinja_env=jinja_env, home=home)
            await message.answer(
                f"{greeting}\n\n{home_text}",
                reply_markup=home_keyboard_from(home),
            )
            return
        if invite_share:
            await mediator.send(
                ExpectInputCommand(
                    telegram_user_id=message.from_user.id,
                    expected_input=ExpectedInput.CODE_OR_LINK,
                    expected_field=f"pending:{invite_share}",
                ),
            )
        elif deep_link:
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
