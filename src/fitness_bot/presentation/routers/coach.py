from __future__ import annotations

from urllib.parse import quote

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.enums import CoachApplicationStatus, ExpectedInput
from fitness_bot.domain.errors import DomainError
from fitness_bot.presentation.keyboards import (
    coach_app_detail_keyboard,
    coach_apply_menu_keyboard,
    coach_apps_keyboard,
    coach_client_proposal_keyboard,
    coach_history_session_keyboard,
    coach_mine_keyboard,
    coach_recent_videos_keyboard,
    coach_session_history_keyboard,
    how_it_works_button,
)
from fitness_bot.presentation.message_draft import (
    NUTRITION_WAITING_PHRASES,
    assistant_parse_failure_text,
    message_draft_scope,
)
from fitness_bot.presentation.routers.program import _can_approve_program, render_proposal
from fitness_bot.service.models.commands.coach import (
    AcceptCoachInviteCommand,
    CreateCoachInviteCommand,
    SetAcceptingClientsCommand,
    StartCoachClientProgramEditCommand,
    UnlinkCoachClientCommand,
)
from fitness_bot.service.models.commands.nutrition import GenerateNutritionCommand
from fitness_bot.service.models.commands.program import ApproveProposalCommand, DiscardProposalCommand
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.coach import (
    GetClientCardQuery,
    GetCoachCabinetQuery,
    GetMyCoachApplicationQuery,
    GetMyCoachQuery,
    ListCoachClientsQuery,
    ListMyCoachApplicationsQuery,
    SearchCoachesQuery,
)
from fitness_bot.service.models.queries.nutrition import GetNutritionQuery
from fitness_bot.service.models.queries.users import GetHomeQuery

_APPLICATION_STATUS_LABELS = {
    CoachApplicationStatus.PENDING: "На проверке",
    CoachApplicationStatus.APPROVED: "Одобрена",
    CoachApplicationStatus.REJECTED: "Отклонена",
}

_bot_username_cache: str | None = None


def _application_status_label(status: CoachApplicationStatus | str) -> str:
    if isinstance(status, str):
        try:
            status = CoachApplicationStatus(status)
        except ValueError:
            return status
    return _APPLICATION_STATUS_LABELS.get(status, str(status))


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _coach_share_code(raw_code: str) -> str:
    """Athlete-facing invite token: c_<CODE> (raw storage has no prefix)."""
    code = raw_code.strip()
    if code.casefold().startswith("c_"):
        return f"c_{code[2:].upper()}"
    return f"c_{code.upper()}"


def _invite_token_from_start_payload(payload: str) -> str | None:
    """Normalize /start payload to c_<CODE> for coach invites (c_… or join_c_… / join_…)."""
    token = payload.strip()
    if not token:
        return None
    lower = token.casefold()
    if lower.startswith("join_"):
        token = token[5:]
        lower = token.casefold()
    if lower.startswith("c_"):
        return _coach_share_code(token)
    # join_<RAW> without c_ prefix
    if payload.strip().casefold().startswith("join_") and token:
        return _coach_share_code(token)
    return None


def _invite_join_start_payload(share_code: str) -> str:
    """Deep-link payload for already-onboarded clients: join_c_<CODE>."""
    return f"join_{_coach_share_code(share_code)}"


def _invite_code_message(raw_code: str, *, regenerated: bool = False) -> str:
    share = _coach_share_code(raw_code)
    title = "Новый код приглашения:" if regenerated else "Код приглашения:"
    return (
        f"{title}\n\n"
        f"<code>{share}</code>\n\n"
        "Отправь этот код клиенту — он введёт его в боте "
        "(«Ввести код или ссылку»).\n"
        "Нажми на код, чтобы скопировать."
    )


async def _resolve_bot_username(bot: Bot) -> str | None:
    """Cache bot username from getMe for deep-link share URLs."""
    global _bot_username_cache
    if _bot_username_cache:
        return _bot_username_cache
    try:
        me = await bot.get_me()
    except Exception:
        return None
    if me.username:
        _bot_username_cache = me.username
        return _bot_username_cache
    return None


def _invite_share_text(
    share_code: str,
    bot_username: str | None,
    *,
    coach_name: str | None,
) -> str:
    """Plain-text body for t.me/share (HTML does not apply in the recipient chat)."""
    name = (coach_name or "").strip() or "тренер"
    share = _coach_share_code(share_code)
    if bot_username:
        bot = bot_username.lstrip("@")
        new_link = f"https://t.me/{bot}?start={share}"
        join_link = f"https://t.me/{bot}?start={_invite_join_start_payload(share)}"
    else:
        new_link = "(ссылка недоступна — открой бота и вставь код)"
        join_link = new_link
    return (
        f"Тренер «{name}» приглашает тебя в AI Fitness.\n\n"
        f"🆕 Ещё не в боте — открой:\n{new_link}\n\n"
        f"✅ Уже в боте — открой:\n{join_link}\n\n"
        f"Или вставь код вручную («Ввести код или ссылку»):\n"
        f"`{share}`"
    )


def _invite_share_url(
    share_code: str,
    bot_username: str | None,
    *,
    coach_name: str | None = None,
) -> str:
    """Native Telegram share sheet: two deep links + pasteable code in text=."""
    share_text = _invite_share_text(share_code, bot_username, coach_name=coach_name)
    if bot_username:
        # Bot home for link preview; labeled deep links live in text=.
        preview_url = f"https://t.me/{bot_username.lstrip('@')}"
    else:
        # Harmless HTTPS placeholder so the picker still opens when username is unknown.
        preview_url = "https://t.me"
    return f"https://t.me/share/url?url={quote(preview_url, safe='')}&text={quote(share_text, safe='')}"


def _invite_share_button(
    share_code: str,
    bot_username: str | None,
    *,
    coach_name: str | None = None,
) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text="📤 Отправить код",
        url=_invite_share_url(share_code, bot_username, coach_name=coach_name),
    )


def _invite_form_keyboard(
    share_code: str,
    bot_username: str | None,
    *,
    coach_name: str | None = None,
) -> InlineKeyboardMarkup:
    return _kb(
        [
            [_invite_share_button(share_code, bot_username, coach_name=coach_name)],
            [InlineKeyboardButton(text="⬅️ Назад в кабинет", callback_data="coach_cab")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
        ],
    )


_INVITE_REGEN_STEPS: dict[int, tuple[str, str, str]] = {
    # step → (body, confirm_label, confirm_callback)
    1: (
        "⚠️ Старый код перестанет работать для новых клиентов: "
        "кто ещё не привязался и у кого на руках старый код — войти по нему уже не получится.",
        "✅ Понятно, дальше",
        "coach_invite_new_2",
    ),
    2: (
        "Уже привязанные клиенты останутся с вами. "
        "❗️ Меняется только код для новых приглашений — старый код вернуть нельзя.",
        "✅ Да, дальше",
        "coach_invite_new_3",
    ),
    3: (
        "❗️ Точно обновить код? Действие необратимо: будет выпущен новый код, старый сразу перестанет действовать.",
        "✅ Да, обновить код",
        "coach_invite_new_ok",
    ),
}


def _invite_regen_confirm_text(step: int) -> str:
    body, _, _ = _INVITE_REGEN_STEPS[step]
    return f"⚠️ Обновление кода\n\n{body}"


def _invite_regen_confirm_keyboard(step: int) -> InlineKeyboardMarkup:
    _, confirm_label, confirm_cb = _INVITE_REGEN_STEPS[step]
    return _kb(
        [
            [InlineKeyboardButton(text=confirm_label, callback_data=confirm_cb)],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="coach_invite_new_cancel")],
            [InlineKeyboardButton(text="🏠 В кабинет", callback_data="coach_cab")],
        ],
    )


def _is_own_invite_code(*, raw_or_share: str, cabinet_invite_code: str | None) -> bool:
    """True when the athlete-facing token matches this coach's active invite."""
    if not cabinet_invite_code:
        return False
    return _coach_share_code(raw_or_share).casefold() == _coach_share_code(cabinet_invite_code).casefold()


async def render_home(
    *,
    message_or_callback,
    jinja_env: Environment,
    mediator: RequestMediator,
    telegram_user_id: int,
) -> None:
    from fitness_bot.presentation.flow_helpers import home_keyboard_from, render_home_text

    home = await mediator.send(GetHomeQuery(telegram_user_id=telegram_user_id))
    text = render_home_text(jinja_env=jinja_env, home=home)
    markup = home_keyboard_from(home)
    if hasattr(message_or_callback, "message") and message_or_callback.message:
        await message_or_callback.message.answer(text, reply_markup=markup)
    else:
        await message_or_callback.answer(text, reply_markup=markup)


def create_coach_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="coach")

    @router.callback_query(F.data == "home")
    async def home(callback: CallbackQuery) -> None:
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.NONE,
            ),
        )
        await render_home(
            message_or_callback=callback,
            jinja_env=jinja_env,
            mediator=mediator,
            telegram_user_id=callback.from_user.id,
        )
        await callback.answer()

    @router.callback_query(F.data == "coach_cab")
    async def cabinet(callback: CallbackQuery) -> None:
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.NONE,
            ),
        )
        result = await mediator.send(GetCoachCabinetQuery(telegram_user_id=callback.from_user.id))
        if not result.verified:
            text = "Кабинет доступен после верификации."
            if result.pending_application:
                text = "Заявка на проверке. Обычно 1–2 дня. Инвайты недоступны."
            await callback.message.answer(text) if callback.message else None
            await callback.answer()
            return
        invite_code = result.invite_code
        if not invite_code:
            try:
                created = await mediator.send(
                    CreateCoachInviteCommand(telegram_user_id=callback.from_user.id),
                )
                invite_code = created.code
            except DomainError as exc:
                if callback.message:
                    await callback.message.answer(str(exc))
                await callback.answer()
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
        if callback.message:
            await callback.message.answer(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data == "coach_invite_show")
    async def invite_show(callback: CallbackQuery) -> None:
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.NONE,
            ),
        )
        cab = await mediator.send(GetCoachCabinetQuery(telegram_user_id=callback.from_user.id))
        invite_code = cab.invite_code
        if not invite_code:
            try:
                created = await mediator.send(
                    CreateCoachInviteCommand(telegram_user_id=callback.from_user.id),
                )
                invite_code = created.code
            except DomainError as exc:
                if callback.message:
                    await callback.message.answer(str(exc))
                await callback.answer()
                return
        share = _coach_share_code(invite_code)
        bot_username = await _resolve_bot_username(callback.bot)
        if callback.message:
            await callback.message.answer(
                _invite_code_message(invite_code),
                reply_markup=_invite_form_keyboard(
                    share,
                    bot_username,
                    coach_name=cab.display_name,
                ),
            )
        await callback.answer()

    async def _answer_invite_form(callback: CallbackQuery) -> None:
        """Re-show current invite form without regenerating (cancel path)."""
        cab = await mediator.send(GetCoachCabinetQuery(telegram_user_id=callback.from_user.id))
        invite_code = cab.invite_code
        if not invite_code:
            if callback.message:
                await callback.message.answer("Код приглашения пока не создан.")
            return
        share = _coach_share_code(invite_code)
        bot_username = await _resolve_bot_username(callback.bot)
        if callback.message:
            await callback.message.answer(
                _invite_code_message(invite_code),
                reply_markup=_invite_form_keyboard(
                    share,
                    bot_username,
                    coach_name=cab.display_name,
                ),
            )

    async def _invite_regen_step(callback: CallbackQuery, step: int) -> None:
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.NONE,
            ),
        )
        if callback.message:
            await callback.message.answer(
                _invite_regen_confirm_text(step),
                reply_markup=_invite_regen_confirm_keyboard(step),
            )
        await callback.answer()

    @router.callback_query(F.data.in_({"coach_invite_new", "coach_invite_new_1"}))
    async def invite_new_step1(callback: CallbackQuery) -> None:
        await _invite_regen_step(callback, 1)

    @router.callback_query(F.data == "coach_invite_new_2")
    async def invite_new_step2(callback: CallbackQuery) -> None:
        await _invite_regen_step(callback, 2)

    @router.callback_query(F.data == "coach_invite_new_3")
    async def invite_new_step3(callback: CallbackQuery) -> None:
        await _invite_regen_step(callback, 3)

    @router.callback_query(F.data == "coach_invite_new_cancel")
    async def invite_new_cancel(callback: CallbackQuery) -> None:
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.NONE,
            ),
        )
        if callback.message:
            await callback.message.answer("Обновление кода отменено.")
        await _answer_invite_form(callback)
        await callback.answer()

    @router.callback_query(F.data == "coach_invite_new_ok")
    async def invite_new_confirm(callback: CallbackQuery) -> None:
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.NONE,
            ),
        )
        markup = None
        try:
            result = await mediator.send(CreateCoachInviteCommand(telegram_user_id=callback.from_user.id))
            text = _invite_code_message(result.code, regenerated=True)
            share = _coach_share_code(result.code)
            bot_username = await _resolve_bot_username(callback.bot)
            cab = await mediator.send(GetCoachCabinetQuery(telegram_user_id=callback.from_user.id))
            markup = _invite_form_keyboard(share, bot_username, coach_name=cab.display_name)
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text, reply_markup=markup)
        await callback.answer()

    @router.callback_query(F.data == "coach_accept_toggle")
    async def toggle_accept(callback: CallbackQuery) -> None:
        cab = await mediator.send(GetCoachCabinetQuery(telegram_user_id=callback.from_user.id))
        try:
            result = await mediator.send(
                SetAcceptingClientsCommand(
                    telegram_user_id=callback.from_user.id,
                    accepting=not cab.accepting_clients,
                ),
            )
            text = f"Принимаю клиентов: {'да' if result.accepting_clients else 'нет'}"
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    @router.callback_query(F.data == "coach_roster")
    async def roster(callback: CallbackQuery) -> None:
        result = await mediator.send(ListCoachClientsQuery(telegram_user_id=callback.from_user.id))
        if not result.items:
            text = "Пока нет подопечных. Поделитесь инвайт-кодом."
            kb = _kb([[InlineKeyboardButton(text="⬅️ Назад", callback_data="coach_cab")]])
        else:
            text = "Клиенты:"
            rows = [
                [
                    InlineKeyboardButton(
                        text=item.display_name,
                        callback_data=f"coach_client:{item.client_user_id}",
                    ),
                ]
                for item in result.items
            ]
            rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="coach_cab")])
            kb = _kb(rows)
        if callback.message:
            await callback.message.answer(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("coach_client:"))
    async def client_card(callback: CallbackQuery) -> None:
        client_id = callback.data.split(":", 1)[1]
        from uuid import UUID

        try:
            card = await mediator.send(
                GetClientCardQuery(telegram_user_id=callback.from_user.id, client_user_id=UUID(client_id)),
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        idle = ""
        if card.idle_badge and card.days_since_last_completed_session is not None:
            idle = f"\n⚠️ Не тренировался {card.days_since_last_completed_session} дн."
        tz = f"\nЧасовой пояс: UTC{card.timezone_offset}" if card.timezone_offset else ""
        text = (
            f"{card.display_name}"
            f"{(' @' + card.telegram_username) if card.telegram_username else ''}"
            f"{tz}{idle}\n"
            f"План: {card.active_program_title or 'нет'}"
        )
        kb = _kb(
            [
                [InlineKeyboardButton(text="Изменить план клиента", callback_data=f"coach_edit:{card.client_user_id}")],
                [InlineKeyboardButton(text="История", callback_data=f"coach_hist:{card.client_user_id}")],
                [
                    InlineKeyboardButton(
                        text="📷 Фото прогресса",
                        callback_data=f"coach_pp_hist:{card.client_user_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text=f"Последние видео ({card.recent_technique_video_count})",
                        callback_data=f"coach_vids:{card.client_user_id}",
                    ),
                ],
                [InlineKeyboardButton(text="Питание", callback_data=f"coach_nutr:{card.client_user_id}")],
                [InlineKeyboardButton(text="Назначить программу", callback_data=f"coach_assign:{card.client_user_id}")],
                [InlineKeyboardButton(text="Отвязать клиента", callback_data=f"coach_unlink:{card.link_id}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="coach_roster")],
            ],
        )
        if callback.message:
            await callback.message.answer(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("coach_unlink:"))
    async def unlink(callback: CallbackQuery) -> None:
        from uuid import UUID

        link_id = UUID(callback.data.split(":", 1)[1])
        try:
            await mediator.send(UnlinkCoachClientCommand(telegram_user_id=callback.from_user.id, link_id=link_id))
            text = "Связь отвязана."
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    @router.callback_query(F.data.startswith("coach_nutr:"))
    async def coach_nutrition(callback: CallbackQuery) -> None:
        from uuid import UUID

        assert callback.from_user is not None
        client_id = UUID(callback.data.split(":", 1)[1])
        back_kb = _kb(
            [[InlineKeyboardButton(text="⬅️ К клиенту", callback_data=f"coach_client:{client_id}")]],
        )

        try:
            status = await mediator.send(
                GetNutritionQuery(
                    telegram_user_id=callback.from_user.id,
                    subject_user_id=client_id,
                ),
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc), reply_markup=back_kb)
            await callback.answer()
            return

        if status.status == "no_program":
            if callback.message:
                await callback.message.answer(
                    "У клиента нет активной программы — питание недоступно.",
                    reply_markup=back_kb,
                )
            await callback.answer()
            return

        if status.status == "current":
            text = jinja_env.get_template("nutrition.j2").render(
                reply="",
                kcal=status.kcal,
                protein_g=status.protein_g,
                fat_g=status.fat_g,
                carb_g=status.carb_g,
                calculation=status.calculation,
                meal_regularity=status.meal_regularity,
                sports_nutrition=status.sports_nutrition,
            )
            if callback.message:
                await callback.message.answer(text, reply_markup=back_kb)
            await callback.answer()
            return

        # missing or stale → generate once (same as athlete «Питание»)
        if callback.message is None:
            await callback.answer()
            return
        await callback.answer()
        draft_preview = ""
        try:
            async with message_draft_scope(
                callback.bot,
                callback.message.chat.id,
                waiting_phrases=NUTRITION_WAITING_PHRASES,
            ) as draft:
                result = await mediator.send(
                    GenerateNutritionCommand(
                        telegram_user_id=callback.from_user.id,
                        subject_user_id=client_id,
                    ),
                )
                draft_preview = draft.preview_text
        except DomainError as exc:
            await callback.message.answer(f"Не удалось посчитать питание: {exc}", reply_markup=back_kb)
            return

        if result.agent_unavailable:
            await callback.message.answer(
                jinja_env.get_template("agent_unavailable.j2").render(),
                reply_markup=back_kb,
            )
            return
        if result.schema_failed or result.kcal is None:
            await callback.message.answer(
                assistant_parse_failure_text(
                    result.reply or draft_preview,
                    hint="Не удалось разобрать ответ помощника. Попробуй ещё раз.",
                ),
                reply_markup=back_kb,
            )
            return

        text = jinja_env.get_template("nutrition.j2").render(
            reply=result.reply,
            kcal=result.kcal,
            protein_g=result.protein_g,
            fat_g=result.fat_g,
            carb_g=result.carb_g,
            calculation=result.calculation,
            meal_regularity=result.meal_regularity,
            sports_nutrition=result.sports_nutrition,
        )
        await callback.message.answer(text, reply_markup=back_kb)
        if result.client_chat_id and callback.bot:
            await callback.bot.send_message(
                result.client_chat_id,
                "Тренер обновил рекомендации по питанию. Откройте раздел «Питание».",
            )

    @router.callback_query(F.data.startswith("coach_assign:"))
    async def coach_assign(callback: CallbackQuery) -> None:
        from fitness_bot.service.models.queries.coach import ListProgramCatalogQuery

        client_id = callback.data.split(":", 1)[1]
        catalog = await mediator.send(ListProgramCatalogQuery(telegram_user_id=callback.from_user.id))
        if not catalog.items:
            text = "Сначала сохраните программу в библиотеку."
            kb = _kb([[InlineKeyboardButton(text="Библиотека", callback_data="library")]])
        else:
            text = "Выберите программу для назначения (as-is):"
            rows = [
                [
                    InlineKeyboardButton(
                        text=item.title,
                        callback_data=f"coach_assign_do:{client_id}:{item.program_id}",
                    ),
                ]
                for item in catalog.items[:10]
            ]
            kb = _kb(rows)
        if callback.message:
            await callback.message.answer(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("coach_assign_do:"))
    async def coach_assign_do(callback: CallbackQuery) -> None:
        from uuid import UUID

        from fitness_bot.service.models.commands.catalog import AssignProgramToClientCommand

        _, client_raw, program_raw = callback.data.split(":", 2)
        try:
            result = await mediator.send(
                AssignProgramToClientCommand(
                    telegram_user_id=callback.from_user.id,
                    client_user_id=UUID(client_raw),
                    program_id=UUID(program_raw),
                    mode="as_is",
                ),
            )
            text = f"Назначено «{result.title}»."
            if callback.bot:
                await callback.bot.send_message(
                    result.client_chat_id,
                    f"Тренер назначил «{result.title}». Открыть мой план: /start",
                )
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    @router.callback_query(F.data.startswith("coach_hist:"))
    async def coach_hist(callback: CallbackQuery) -> None:
        from uuid import UUID

        from fitness_bot.service.models.queries.session import GetSessionHistoryQuery

        parts = callback.data.split(":")
        client_id = UUID(parts[1])
        offset = int(parts[2]) if len(parts) > 2 else 0
        try:
            history = await mediator.send(
                GetSessionHistoryQuery(
                    telegram_user_id=callback.from_user.id,
                    subject_user_id=client_id,
                    offset=offset,
                ),
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        if not history.items:
            text = "У клиента пока нет завершённых тренировок."
            kb = _kb([[InlineKeyboardButton(text="⬅️ К клиенту", callback_data=f"coach_client:{client_id}")]])
        else:
            text = "История тренировок клиента:"
            kb = coach_session_history_keyboard(
                client_user_id=str(client_id),
                items=[
                    (
                        str(item.session_id),
                        item.title
                        if not item.completed_at
                        else f"{item.title} · {item.completed_at.strftime('%d.%m.%Y')}",
                    )
                    for item in history.items
                ],
                offset=history.offset,
                has_more=history.has_more,
            )
        if callback.message:
            await callback.message.answer(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("coach_hist_one:"))
    async def coach_hist_one(callback: CallbackQuery) -> None:
        from uuid import UUID

        from fitness_bot.service.models.queries.session import GetSessionDetailQuery

        _, client_raw, session_raw = callback.data.split(":", 2)
        client_id = UUID(client_raw)
        session_id = UUID(session_raw)
        try:
            detail = await mediator.send(
                GetSessionDetailQuery(
                    telegram_user_id=callback.from_user.id,
                    session_id=session_id,
                    subject_user_id=client_id,
                ),
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        watch_items = [
            (
                str(slot.slot_id),
                slot.exercise_name or slot.custom_request or f"№{slot.position}",
            )
            for slot in detail.slots
            if slot.has_technique_video
        ]
        lines = [f"{detail.title}"]
        if detail.completed_at:
            lines.append(detail.completed_at.strftime("%d.%m.%Y %H:%M"))
        for slot in detail.slots:
            name = slot.exercise_name or slot.custom_request or f"Слот {slot.position}"
            marker = " 🎥" if slot.has_technique_video else ""
            lines.append(f"• {name}{marker}")
        text = "\n".join(lines)
        kb = coach_history_session_keyboard(client_user_id=str(client_id), watch_items=watch_items)
        if callback.message:
            await callback.message.answer(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("coach_hist_vid:"))
    async def coach_hist_vid(callback: CallbackQuery) -> None:
        from uuid import UUID

        from aiogram.types import BufferedInputFile

        from fitness_bot.service.models.queries.session import PrepareTechniqueVideoDeliveryQuery

        _, client_raw, slot_raw = callback.data.split(":", 2)
        client_id = UUID(client_raw)
        slot_id = UUID(slot_raw)
        delivery = await mediator.send(
            PrepareTechniqueVideoDeliveryQuery(
                telegram_user_id=callback.from_user.id,
                slot_id=slot_id,
                subject_user_id=client_id,
            ),
        )
        if delivery.missing:
            if callback.message:
                await callback.message.answer("Видео недоступно.")
            await callback.answer()
            return
        try:
            if delivery.telegram_file_id and callback.message:
                await callback.message.answer_video(delivery.telegram_file_id, caption=delivery.exercise_name)
            elif delivery.body is not None and callback.message:
                await callback.message.answer_video(
                    BufferedInputFile(delivery.body, filename="technique.mp4"),
                    caption=delivery.exercise_name,
                )
            await callback.answer()
        except Exception:
            if callback.message:
                await callback.message.answer("Не удалось отправить видео.")
            await callback.answer()

    @router.callback_query(F.data.startswith("coach_vids:"))
    async def coach_vids(callback: CallbackQuery) -> None:
        from uuid import UUID

        from fitness_bot.service.models.queries.session import ListClientRecentVideosQuery

        client_id = UUID(callback.data.split(":", 1)[1])
        try:
            result = await mediator.send(
                ListClientRecentVideosQuery(
                    telegram_user_id=callback.from_user.id,
                    client_user_id=client_id,
                ),
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        if not result.items:
            text = "Пока нет видео техники."
            kb = _kb([[InlineKeyboardButton(text="⬅️ К клиенту", callback_data=f"coach_client:{client_id}")]])
        else:
            text = f"Последние видео ({result.total_count}):"
            kb = coach_recent_videos_keyboard(
                client_user_id=str(client_id),
                items=[
                    (
                        str(item.slot_id),
                        item.exercise_name or item.session_title,
                    )
                    for item in result.items
                ],
            )
        if callback.message:
            await callback.message.answer(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("coach_edit:"))
    async def coach_edit_start(callback: CallbackQuery) -> None:
        from uuid import UUID

        client_id = UUID(callback.data.split(":", 1)[1])
        try:
            result = await mediator.send(
                StartCoachClientProgramEditCommand(
                    telegram_user_id=callback.from_user.id,
                    client_user_id=client_id,
                ),
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        hint = (
            "Черновик плана клиента готов. Опишите правки текстом — "
            "после подтверждения план сразу станет активным у клиента."
            if result.has_active_program
            else "У клиента нет активного плана. Опишите программу текстом, затем подтвердите."
        )
        can_approve = bool(result.document and result.document.days and _can_approve_program(result.document))
        if callback.message and result.document is not None:
            await render_proposal(
                jinja_env=jinja_env,
                mediator=mediator,
                message=callback.message,
                reply=hint,
                document=result.document,
                program_type=result.program_type,
                telegram_user_id=callback.from_user.id,
                reply_markup=coach_client_proposal_keyboard(
                    client_user_id=str(client_id),
                    can_approve=can_approve,
                ),
            )
        elif callback.message:
            await callback.message.answer(
                hint,
                reply_markup=coach_client_proposal_keyboard(
                    client_user_id=str(client_id),
                    can_approve=False,
                ),
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("coach_prog_ok:"))
    async def coach_prog_ok(callback: CallbackQuery) -> None:
        from uuid import UUID

        client_id = UUID(callback.data.split(":", 1)[1])
        try:
            result = await mediator.send(
                ApproveProposalCommand(
                    telegram_user_id=callback.from_user.id,
                    subject_user_id=client_id,
                ),
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        if result.blocked_empty or result.blocked_unresolved or result.blocked_schedule:
            text = "План ещё нельзя применить — доработайте черновик."
        else:
            title = result.program_title or "План"
            text = f"План клиента обновлён: «{title}»."
            if result.client_chat_id and callback.bot:
                await callback.bot.send_message(
                    result.client_chat_id,
                    f"Тренер обновил ваш план «{title}». Открыть мой план: /start",
                    reply_markup=_kb(
                        [[InlineKeyboardButton(text="📋 Мой план сейчас", callback_data="prog")]],
                    ),
                )
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    @router.callback_query(F.data.startswith("coach_prog_cancel:"))
    async def coach_prog_cancel(callback: CallbackQuery) -> None:
        from uuid import UUID

        client_id = UUID(callback.data.split(":", 1)[1])
        try:
            await mediator.send(
                DiscardProposalCommand(
                    telegram_user_id=callback.from_user.id,
                    subject_user_id=client_id,
                ),
            )
            text = "Правка отменена."
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    @router.callback_query(F.data == "coach_mine")
    async def coach_mine(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        result = await mediator.send(GetMyCoachQuery(telegram_user_id=callback.from_user.id))
        text = jinja_env.get_template("coach_mine.j2").render(
            linked=result.linked,
            display_name=result.display_name,
            bio=result.bio,
            rating_avg=result.rating_avg,
            rating_count=result.rating_count,
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
        if callback.message:
            await callback.message.answer(text, reply_markup=markup)
        await callback.answer()

    @router.callback_query(F.data == "coach_mine_unlink")
    async def coach_mine_unlink(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        try:
            await mediator.send(UnlinkCoachClientCommand(telegram_user_id=callback.from_user.id))
            text = "Связь с тренером отвязана."
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await render_home(
            message_or_callback=callback,
            jinja_env=jinja_env,
            mediator=mediator,
            telegram_user_id=callback.from_user.id,
        )
        await callback.answer()

    @router.callback_query(F.data == "coach_search")
    async def search(callback: CallbackQuery) -> None:
        result = await mediator.send(SearchCoachesQuery(telegram_user_id=callback.from_user.id))
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
            rows = []
            for item in result.items:
                stars = f"★{item.rating_avg}" if item.rating_avg is not None else "★—"
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"{item.display_name} {stars} ({item.rating_count})",
                            callback_data=f"coach_card:{item.user_id}",
                        ),
                    ],
                )
            rows.append([how_it_works_button("coach_search")])
            rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="home")])
            kb = _kb(rows)
        if callback.message:
            await callback.message.answer(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data == "coach_apply")
    async def apply_menu(callback: CallbackQuery) -> None:
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.NONE,
            ),
        )
        if callback.message:
            await callback.message.answer(
                "Стать тренером\n\nПодайте заявку или посмотрите статус уже отправленных.",
                reply_markup=coach_apply_menu_keyboard(),
            )
        await callback.answer()

    @router.callback_query(F.data == "coach_apply_start")
    async def apply_start(callback: CallbackQuery) -> None:
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.COACH_APPLICATION,
                expected_field="1:name_bio",
            ),
        )
        if callback.message:
            await callback.message.answer(
                "Заявка 1/3: отправьте имя и био в одном сообщении (имя на первой строке).",
                reply_markup=_kb([[InlineKeyboardButton(text="❌ Отмена", callback_data="home")]]),
            )
        await callback.answer()

    @router.callback_query(F.data == "coach_apps")
    async def my_applications(callback: CallbackQuery) -> None:
        result = await mediator.send(ListMyCoachApplicationsQuery(telegram_user_id=callback.from_user.id))
        if not result.items:
            text = "Пока нет заявок."
            kb = coach_apps_keyboard(items=[])
        else:
            text = "Мои заявки:"
            items: list[tuple[str, str]] = []
            for item in result.items:
                status = _application_status_label(item.status)
                date = item.created_at.strftime("%d.%m.%Y")
                name = item.display_name.strip() or "Без имени"
                if len(name) > 24:
                    name = name[:23] + "…"
                items.append((str(item.application_id), f"{status} · {name} · {date}"))
            kb = coach_apps_keyboard(items=items)
        if callback.message:
            await callback.message.answer(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("coach_app:"))
    async def application_detail(callback: CallbackQuery) -> None:
        from uuid import UUID

        application_id = UUID(callback.data.split(":", 1)[1])
        try:
            detail = await mediator.send(
                GetMyCoachApplicationQuery(
                    telegram_user_id=callback.from_user.id,
                    application_id=application_id,
                ),
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc), reply_markup=coach_app_detail_keyboard())
            await callback.answer()
            return
        status = _application_status_label(detail.status)
        lines = [
            "Заявка",
            "",
            f"Статус: {status}",
            f"Имя: {detail.display_name}",
            f"Подана: {detail.created_at.strftime('%d.%m.%Y %H:%M')}",
        ]
        if detail.status == CoachApplicationStatus.REJECTED and detail.moderator_comment:
            lines.append(f"Комментарий: {detail.moderator_comment}")
        elif detail.resolved_at is not None:
            lines.append(f"Решена: {detail.resolved_at.strftime('%d.%m.%Y %H:%M')}")
        if callback.message:
            await callback.message.answer("\n".join(lines), reply_markup=coach_app_detail_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "code_link")
    async def code_or_link(callback: CallbackQuery) -> None:
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.CODE_OR_LINK,
            ),
        )
        if callback.message:
            await callback.message.answer(
                "Введите код или ссылку (программа p_… / тренер c_…).",
                reply_markup=_kb([[InlineKeyboardButton(text="❌ Отмена", callback_data="home")]]),
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("coach_accept:"))
    async def accept_invite(callback: CallbackQuery) -> None:
        code = callback.data.split(":", 1)[1]
        try:
            result = await mediator.send(
                AcceptCoachInviteCommand(telegram_user_id=callback.from_user.id, code=code),
            )
            text = "Тренер подключён. Он видит прогресс, замеры и видео техники."
            if result.previous_coach_user_id:
                text += "\nПрежняя связь отвязана. Оценить прежнего тренера?"
        except DomainError as exc:
            if "yourself" in str(exc):
                text = "Это ваш код приглашения, отправьте его клиенту."
            else:
                text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    return router
