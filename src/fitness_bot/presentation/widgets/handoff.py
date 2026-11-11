"""Leave the widget bubble and draw a classic keyboard screen."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from cqrs import RequestMediator

from fitness_bot.domain.errors import DomainError
from fitness_bot.presentation.keyboards import (
    coach_apply_menu_keyboard,
    coach_mine_keyboard,
    how_it_works_button,
    profile_hub_keyboard,
)
from fitness_bot.presentation.templates_env import create_jinja_env
from fitness_bot.service.models.commands.coach import CreateCoachInviteCommand
from fitness_bot.service.models.queries.coach import (
    GetCoachCabinetQuery,
    GetMyCoachQuery,
    ListPendingCoachApplicationsQuery,
    SearchCoachesQuery,
)

_HAND_OFFS = frozenset({"profile", "coach_mine", "coach_search", "coach_cab", "coach_apply", "mod"})


def known_handoff(target: str) -> bool:
    return target in _HAND_OFFS


async def deliver_handoff(
    *,
    bot: object,
    mediator: RequestMediator,
    user_id: int,
    chat_id: int,
    target: str,
) -> None:
    if not known_handoff(target) or not callable(getattr(bot, "send_message", None)):
        return
    if target == "profile":
        await _profile(bot, mediator, user_id, chat_id)
        return
    if target == "coach_mine":
        await _coach_mine(bot, mediator, user_id, chat_id)
        return
    if target == "coach_search":
        await _coach_search(bot, mediator, user_id, chat_id)
        return
    if target == "coach_cab":
        await _coach_cab(bot, mediator, user_id, chat_id)
        return
    if target == "coach_apply":
        await bot.send_message(
            chat_id,
            "Стать тренером\n\nПодайте заявку или посмотрите статус уже отправленных.",
            reply_markup=coach_apply_menu_keyboard(),
        )
        return
    await _mod(bot, mediator, user_id, chat_id)


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _profile(bot: object, mediator: RequestMediator, user_id: int, chat_id: int) -> None:
    from fitness_bot.presentation.routers.profile import profile_hub_text

    text = await profile_hub_text(jinja_env=create_jinja_env(), mediator=mediator, telegram_user_id=user_id)
    await bot.send_message(chat_id, text, reply_markup=profile_hub_keyboard())


async def _coach_mine(bot: object, mediator: RequestMediator, user_id: int, chat_id: int) -> None:
    result = await mediator.send(GetMyCoachQuery(telegram_user_id=user_id))
    text = (
        create_jinja_env()
        .get_template("coach_mine.j2")
        .render(
            linked=result.linked,
            display_name=result.display_name,
            bio=result.bio,
            rating_avg=result.rating_avg,
            rating_count=result.rating_count,
        )
    )
    markup = (
        coach_mine_keyboard()
        if result.linked
        else _kb(
            [
                [InlineKeyboardButton(text="🔎 Найти тренера", callback_data="coach_search")],
                [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
            ],
        )
    )
    await bot.send_message(chat_id, text, reply_markup=markup)


async def _coach_search(bot: object, mediator: RequestMediator, user_id: int, chat_id: int) -> None:
    result = await mediator.send(SearchCoachesQuery(telegram_user_id=user_id))
    if not result.items:
        text = "Пока нет тренеров — вставь код, если есть."
        kb = _kb(
            [
                [InlineKeyboardButton(text="Ввести код", callback_data="code_link")],
                [how_it_works_button("coach_search")],
                [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
            ],
        )
    else:
        text = "Тренеры:"
        rows = [
            [
                InlineKeyboardButton(
                    text=(
                        f"{item.display_name} "
                        f"{'★' + str(item.rating_avg) if item.rating_avg is not None else '★—'} "
                        f"({item.rating_count})"
                    ),
                    callback_data=f"coach_card:{item.user_id}",
                ),
            ]
            for item in result.items
        ]
        rows.append([how_it_works_button("coach_search")])
        rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="home")])
        kb = _kb(rows)
    await bot.send_message(chat_id, text, reply_markup=kb)


async def _coach_cab(bot: object, mediator: RequestMediator, user_id: int, chat_id: int) -> None:
    from fitness_bot.presentation.routers.coach import _coach_share_code

    result = await mediator.send(GetCoachCabinetQuery(telegram_user_id=user_id))
    if not result.verified:
        text = "Кабинет доступен после верификации."
        if result.pending_application:
            text = "Заявка на проверке. Обычно 1–2 дня. Инвайты недоступны."
        await bot.send_message(
            chat_id,
            text,
            reply_markup=_kb([[InlineKeyboardButton(text="🏠 В меню", callback_data="home")]]),
        )
        return
    invite_code = result.invite_code
    if not invite_code:
        try:
            created = await mediator.send(CreateCoachInviteCommand(telegram_user_id=user_id))
            invite_code = created.code
        except DomainError as exc:
            await bot.send_message(chat_id, str(exc))
            return
    share = _coach_share_code(invite_code)
    text = (
        f"Кабинет тренера\n"
        f"Подопечных: {result.active_clients}\n"
        f"Принимаю клиентов: {'да' if result.accepting_clients else 'нет'}\n\n"
        f"Код для клиента:\n<code>{share}</code>\n\n"
        "Отправь этот код клиенту — он вставит его через «Ввести код или ссылку».\n"
        "Нажми на код, чтобы скопировать."
    )
    kb = _kb(
        [
            [InlineKeyboardButton(text="Мои клиенты", callback_data="coach_roster")],
            [InlineKeyboardButton(text="📩 Код приглашения", callback_data="coach_invite_show")],
            [InlineKeyboardButton(text="Обновить код", callback_data="coach_invite_new")],
            [
                InlineKeyboardButton(
                    text="Принимаю ✓" if result.accepting_clients else "Не принимаю",
                    callback_data="coach_accept_toggle",
                ),
            ],
            [InlineKeyboardButton(text="📚 Библиотека", callback_data="library")],
            [how_it_works_button("coach_cab")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
        ],
    )
    await bot.send_message(chat_id, text, reply_markup=kb)


async def _mod(bot: object, mediator: RequestMediator, user_id: int, chat_id: int) -> None:
    try:
        result = await mediator.send(ListPendingCoachApplicationsQuery(telegram_user_id=user_id))
    except DomainError as exc:
        await bot.send_message(chat_id, str(exc))
        return
    if not result.items:
        text = "Очередь заявок пуста."
        kb = _kb(
            [
                [InlineKeyboardButton(text="Модераторы", callback_data="mod_list")],
                [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
            ],
        )
    else:
        text = "Заявки на статус тренера:"
        rows = [
            [InlineKeyboardButton(text=item.display_name, callback_data=f"mod_app:{item.application_id}")]
            for item in result.items
        ]
        rows.append([InlineKeyboardButton(text="Модераторы", callback_data="mod_list")])
        rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="home")])
        kb = _kb(rows)
    await bot.send_message(chat_id, text, reply_markup=kb)
