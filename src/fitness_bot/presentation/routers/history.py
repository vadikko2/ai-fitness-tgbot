from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.errors import DomainError
from fitness_bot.presentation.keyboards import (
    back_to_menu_keyboard,
    history_menu_keyboard,
    history_session_keyboard,
    session_history_keyboard,
)
from fitness_bot.service.models.commands.session import RememberTechniqueVideoFileIdCommand
from fitness_bot.service.models.queries.body import GetMeasurementHistoryQuery, GetWeightHistoryQuery
from fitness_bot.service.models.queries.session import (
    GetSessionDetailQuery,
    GetSessionHistoryQuery,
    PrepareTechniqueVideoDeliveryQuery,
)


def create_history_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="history")

    async def _answer(callback: CallbackQuery, text: str, **kwargs) -> None:
        if callback.message:
            await callback.message.answer(text, reply_markup=kwargs.get("reply_markup"))
        await callback.answer()

    @router.callback_query(F.data == "hist")
    async def handle_hist(callback: CallbackQuery) -> None:
        text = jinja_env.get_template("history_menu.j2").render()
        await _answer(callback, text, reply_markup=history_menu_keyboard())

    @router.callback_query(F.data.startswith("hist_sess"))
    async def handle_hist_sess(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        offset = 0
        if ":" in callback.data:
            offset = int(callback.data.split(":", 1)[1])
        history = await mediator.send(
            GetSessionHistoryQuery(telegram_user_id=callback.from_user.id, offset=offset),
        )
        text = jinja_env.get_template("history_sessions.j2").render(items=history.items)
        markup = session_history_keyboard(
            items=[
                (
                    str(item.session_id),
                    item.title if not item.completed_at else f"{item.title} · {item.completed_at.strftime('%d.%m.%Y')}",
                )
                for item in history.items
            ],
            offset=history.offset,
            has_more=history.has_more,
        )
        await _answer(callback, text, reply_markup=markup)

    @router.callback_query(F.data == "hist_wt")
    async def handle_hist_wt(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        history = await mediator.send(GetWeightHistoryQuery(telegram_user_id=callback.from_user.id))
        text = jinja_env.get_template("weight_history.j2").render(items=history.items)
        await _answer(callback, text, reply_markup=back_to_menu_keyboard())

    @router.callback_query(F.data == "hist_meas")
    async def handle_hist_meas(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        history = await mediator.send(GetMeasurementHistoryQuery(telegram_user_id=callback.from_user.id))
        text = jinja_env.get_template("history.j2").render(entries=history.entries, site_name=None)
        await _answer(callback, text, reply_markup=back_to_menu_keyboard())

    @router.callback_query(F.data.startswith("hist_one:"))
    async def handle_hist_one(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        session_id = UUID(callback.data.split(":", 1)[1])
        try:
            detail = await mediator.send(
                GetSessionDetailQuery(telegram_user_id=callback.from_user.id, session_id=session_id),
            )
        except DomainError as exc:
            await _answer(callback, f"Не удалось открыть тренировку: {exc}")
            return
        watch_items = [
            (
                str(slot.slot_id),
                slot.exercise_name or slot.custom_request or f"№{slot.position}",
            )
            for slot in detail.slots
            if slot.has_technique_video
        ]
        text = jinja_env.get_template("history_session.j2").render(
            title=detail.title,
            completed_at=detail.completed_at,
            has_watch_videos=bool(watch_items),
            slots=[
                {
                    "slot_id": str(slot.slot_id),
                    "position": slot.position,
                    "exercise_name": slot.exercise_name,
                    "custom_request": slot.custom_request,
                    "actual": slot.actual,
                    "has_technique_video": slot.has_technique_video,
                }
                for slot in detail.slots
            ],
        )
        await _answer(callback, text, reply_markup=history_session_keyboard(watch_items=watch_items))

    @router.callback_query(F.data.startswith("hist_vid:"))
    async def handle_hist_vid(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        assert callback.message is not None
        slot_id = UUID(callback.data.split(":", 1)[1])
        delivery = await mediator.send(
            PrepareTechniqueVideoDeliveryQuery(
                telegram_user_id=callback.from_user.id,
                slot_id=slot_id,
            ),
        )
        if delivery.missing:
            text = jinja_env.get_template("technique_video_failed.j2").render()
            await _answer(callback, text)
            return
        try:
            if delivery.telegram_file_id:
                if callback.message:
                    await callback.message.answer_video(delivery.telegram_file_id, caption=delivery.exercise_name)
                await callback.answer()
            else:
                assert delivery.body is not None
                sent = (
                    await callback.message.answer_video(
                        BufferedInputFile(delivery.body, filename="technique.mp4"),
                        caption=delivery.exercise_name,
                    )
                    if callback.message
                    else None
                )
                await callback.answer()
                file_id = None
                if sent is not None:
                    if sent.video is not None:
                        file_id = sent.video.file_id
                    elif sent.video_note is not None:
                        file_id = sent.video_note.file_id
                if file_id:
                    await mediator.send(
                        RememberTechniqueVideoFileIdCommand(
                            telegram_user_id=callback.from_user.id,
                            slot_id=slot_id,
                            telegram_file_id=file_id,
                        ),
                    )
        except Exception:
            text = jinja_env.get_template("technique_video_failed.j2").render()
            await _answer(callback, text)
            return

    return router
