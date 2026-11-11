"""The only entry routers use to open a widget, answer a tap, or redraw after text."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from cqrs import RequestMediator

from fitness_bot.presentation.chat_pages import leave_page, remember
from fitness_bot.presentation.widgets.frame import (
    WIDGET_HEIGHT,
    WidgetBinding,
    WidgetBindings,
    WidgetFrame,
    WidgetScreenId,
)
from fitness_bot.presentation.widgets.limits import WidgetLimitError
from fitness_bot.presentation.widgets.opcodes import OpcodeRejection, parse_opcode
from fitness_bot.presentation.widgets.screen import ScreenContext, ScreenResult, WidgetScreen
from fitness_bot.presentation.widgets.transport import (
    AiogramCompanionMedia,
    AiogramWidgetTransport,
    CompanionMedia,
    WidgetTransport,
)

logger = logging.getLogger(__name__)

BAD_WIDGET_ANSWER = '{"err":"bad"}'


class WidgetFlags(Protocol):
    widgets_enabled: bool


@dataclass(frozen=True, slots=True)
class WidgetQuery:
    query_id: str
    user_id: int
    chat_id: int
    message_id: int
    data: str


@dataclass(frozen=True, slots=True)
class OpenResult:
    """``use_keyboard`` tells the caller to draw the current inline-keyboard screen."""

    use_keyboard: bool
    message_id: int | None = None
    frame: WidgetFrame | None = None


_current: WidgetGateway | None = None


class WidgetGateway:
    def __init__(
        self,
        *,
        transport: WidgetTransport,
        media: CompanionMedia,
        bindings: WidgetBindings,
        mediator: RequestMediator,
        settings: WidgetFlags,
        screens: dict[WidgetScreenId, WidgetScreen] | None = None,
        bot: object | None = None,
    ) -> None:
        self._transport = transport
        self._media = media
        self._bindings = bindings
        self._mediator = mediator
        self._settings = settings
        self._screens: dict[WidgetScreenId, WidgetScreen] = dict(screens or {})
        self._bot = bot

    @property
    def bindings(self) -> WidgetBindings:
        return self._bindings

    def register_screen(self, screen: WidgetScreen) -> None:
        self._screens[screen.screen_id] = screen

    async def open(
        self,
        user_id: int,
        screen: WidgetScreenId,
        *,
        chat_id: int | None = None,
    ) -> OpenResult:
        if not self._settings.widgets_enabled:
            return OpenResult(use_keyboard=True)
        widget = self._screens.get(screen)
        if widget is None:
            logger.warning("widget screen %s is not registered", screen.value)
            return OpenResult(use_keyboard=True)
        resolved_chat = user_id if chat_id is None else chat_id
        ctx = ScreenContext(
            user_id=user_id,
            binding=WidgetBinding(chat_id=resolved_chat, message_id=0, screen=screen),
            mediator=self._mediator,
        )
        frame = await widget.open(ctx)
        html_for = getattr(widget, "html_for", None)
        try:
            html = await html_for(ctx) if callable(html_for) else widget.shell.html()
        except Exception:
            logger.warning("widget html failed; using the default shell", exc_info=True)
            html = widget.shell.html()
        try:
            await leave_page(self._bot, user_id)
            prelude = WidgetBinding(chat_id=resolved_chat, message_id=0, screen=screen, frame=frame)
            prelude = await self._companion_binding(user_id, prelude, widget, ctx, frame)
            message_id = await self._transport.send(
                resolved_chat,
                html=html,
                chat_data=frame.chat_data,
                caption=frame.caption,
                height=WIDGET_HEIGHT[frame.screen],
            )
        except (WidgetLimitError, TelegramAPIError, RuntimeError):
            logger.warning("widget open failed; caller should draw the keyboard", exc_info=True)
            return OpenResult(use_keyboard=True)
        binding = WidgetBinding(
            chat_id=resolved_chat,
            message_id=message_id,
            screen=screen,
            video_message_id=prelude.video_message_id,
            frame=frame,
        )
        self._bindings.put(user_id, binding)
        remember(user_id, resolved_chat, message_id)
        return OpenResult(use_keyboard=False, message_id=message_id, frame=frame)

    async def on_query(self, query: WidgetQuery) -> None:
        found = self._bindings.lookup(query.chat_id, query.message_id)
        if found is None or found[0] != query.user_id:
            await self.reject(query.query_id)
            return
        user_id, binding = found
        parsed = parse_opcode(query.data)
        if isinstance(parsed, OpcodeRejection) or parsed.screen != binding.screen:
            await self.reject(query.query_id)
            return
        widget = self._screens.get(binding.screen)
        if widget is None:
            await self.reject(query.query_id)
            return
        ctx = ScreenContext(user_id=user_id, binding=binding, mediator=self._mediator)
        result = await widget.apply(ctx, query.data)
        if result.expect is not None:
            await self._mediator.send(result.expect)
        if result.navigate is not None:
            await self._transport.answer(query.query_id, result.answer)
            await self.open(user_id, result.navigate, chat_id=binding.chat_id)
            return
        binding = await self._sync_media(user_id, binding, result)
        await self._transport.edit_state(binding.chat_id, binding.message_id, result.frame.chat_data)
        if binding.frame is None or binding.frame.caption != result.frame.caption:
            await self._transport.edit_caption(binding.chat_id, binding.message_id, result.frame.caption)
        self._bindings.put(user_id, replace(binding, frame=result.frame))
        await self._transport.answer(query.query_id, result.answer)

    async def refresh(self, user_id: int) -> WidgetFrame | None:
        binding = self._bindings.get(user_id)
        if binding is None:
            return None
        widget = self._screens.get(binding.screen)
        if widget is None:
            return None
        ctx = ScreenContext(user_id=user_id, binding=binding, mediator=self._mediator)
        frame = await widget.open(ctx)
        binding = await self._companion_binding(user_id, binding, widget, ctx, frame)
        await self._transport.edit_state(binding.chat_id, binding.message_id, frame.chat_data)
        if binding.frame is None or binding.frame.caption != frame.caption:
            await self._transport.edit_caption(binding.chat_id, binding.message_id, frame.caption)
        self._bindings.put(user_id, replace(binding, frame=frame))
        return frame

    async def reject(self, query_id: str) -> None:
        await self._transport.answer(query_id, BAD_WIDGET_ANSWER)

    async def _companion_binding(
        self,
        user_id: int,
        binding: WidgetBinding,
        widget: WidgetScreen,
        ctx: ScreenContext,
        frame: WidgetFrame,
    ) -> WidgetBinding:
        companion = getattr(widget, "companion", None)
        if not callable(companion):
            return binding
        try:
            media_result = await companion(ctx, frame)
        except Exception:
            logger.warning("widget companion failed", exc_info=True)
            return binding
        if media_result is None:
            return binding
        try:
            return await self._sync_media(user_id, binding, media_result)
        except (TelegramAPIError, OSError, ValueError):
            logger.warning("widget companion failed", exc_info=True)
            return binding

    async def _sync_media(self, user_id: int, binding: WidgetBinding, result: ScreenResult) -> WidgetBinding:
        if result.video_file_id:
            kind, file_id, path = "video", result.video_file_id, None
        elif result.photo_path:
            kind, file_id, path = "photo", None, result.photo_path
        elif result.clear_video:
            return replace(binding, video_message_id=None)
        else:
            return binding
        message_id = await self._media.upsert(
            binding.chat_id,
            message_id=None if result.clear_video else binding.video_message_id,
            kind=kind,
            file_id=file_id,
            path=path,
            cover_file_id=result.cover_file_id,
            caption=result.frame.caption,
        )
        remember(user_id, binding.chat_id, message_id)
        return replace(binding, video_message_id=message_id)


def build_widget_gateway(
    *,
    bot: Bot,
    mediator: RequestMediator,
    settings: WidgetFlags,
) -> WidgetGateway:
    gateway = WidgetGateway(
        transport=AiogramWidgetTransport(bot),
        media=AiogramCompanionMedia(bot),
        bindings=WidgetBindings(),
        mediator=mediator,
        settings=settings,
        bot=bot,
    )
    from fitness_bot.presentation.widgets.screens import register_widget_screens

    register_widget_screens(gateway)
    return gateway


def install_widget_gateway(gateway: WidgetGateway) -> None:
    global _current
    _current = gateway


def widget_gateway() -> WidgetGateway | None:
    return _current
