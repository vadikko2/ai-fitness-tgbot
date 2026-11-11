"""Bot API 10.4 widget calls. aiogram 3.31 has no widget methods, so this posts them raw."""

from __future__ import annotations

from typing import Any, Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods.base import TelegramMethod
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo
from aiohttp import ClientError

from fitness_bot.presentation.widgets.glyphs import remember_glyph_cover
from fitness_bot.presentation.widgets.limits import ensure_widget_html, ensure_widget_state

_NOT_MODIFIED = "message is not modified"


class WidgetTransport(Protocol):
    async def send(
        self,
        chat_id: int,
        *,
        html: str,
        chat_data: str,
        caption: str,
        height: int,
    ) -> int:
        """sendWidget with allow_queries, without is_shared. Return message_id."""

    async def edit_state(self, chat_id: int, message_id: int, chat_data: str) -> None:
        """editMessageWidgetData. An empty diff is not an error."""

    async def edit_caption(self, chat_id: int, message_id: int, caption: str) -> None:
        """editMessageCaption. Caption is the text for the chat list and old clients."""

    async def answer(self, query_id: str, data: str | None) -> None:
        """answerWidgetQuery. data is up to 1024 bytes, or None."""


class CompanionMedia(Protocol):
    async def upsert(
        self,
        chat_id: int,
        *,
        message_id: int | None,
        kind: str,
        file_id: str | None,
        path: str | None,
        cover_file_id: str | None,
        caption: str,
    ) -> int:
        """Photo or video. Video passes the glyph cover file_id and supports_streaming.

        An empty message_id sends; otherwise the same bubble is edited.
        """


class _SendWidget(TelegramMethod[Any]):
    __returning__ = Any
    __api_method__ = "sendWidget"


class _EditWidgetData(TelegramMethod[Any]):
    __returning__ = Any
    __api_method__ = "editMessageWidgetData"


class _AnswerWidgetQuery(TelegramMethod[Any]):
    __returning__ = Any
    __api_method__ = "answerWidgetQuery"


class _EditCaption(TelegramMethod[Any]):
    __returning__ = Any
    __api_method__ = "editMessageCaption"


_METHOD_TYPES: dict[str, type[TelegramMethod[Any]]] = {
    "sendWidget": _SendWidget,
    "editMessageWidgetData": _EditWidgetData,
    "answerWidgetQuery": _AnswerWidgetQuery,
    "editMessageCaption": _EditCaption,
}


def _plain_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _message_id(result: object) -> int:
    if isinstance(result, dict):
        value = result.get("message_id")
    else:
        value = getattr(result, "message_id", None)
    message_id = _plain_int(value)
    if message_id is None:
        msg = "sendWidget returned no message_id"
        raise RuntimeError(msg)
    return message_id


class AiogramWidgetTransport:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send(
        self,
        chat_id: int,
        *,
        html: str,
        chat_data: str,
        caption: str,
        height: int,
    ) -> int:
        ensure_widget_html(html)
        ensure_widget_state(chat_data, what="chat_data")
        result = await self._request(
            "sendWidget",
            {
                "chat_id": chat_id,
                "html": html,
                "chat_data": chat_data,
                "caption": caption,
                "height": height,
                "width": 0,
                "allow_queries": True,
                "is_shared": False,
            },
        )
        return _message_id(result)

    async def edit_state(self, chat_id: int, message_id: int, chat_data: str) -> None:
        ensure_widget_state(chat_data, what="chat_data")
        await self._edit(
            "editMessageWidgetData",
            {"chat_id": chat_id, "message_id": message_id, "chat_data": chat_data},
        )

    async def edit_caption(self, chat_id: int, message_id: int, caption: str) -> None:
        await self._edit(
            "editMessageCaption",
            {"chat_id": chat_id, "message_id": message_id, "caption": caption},
        )

    async def answer(self, query_id: str, data: str | None) -> None:
        payload: dict[str, object] = {"widget_query_id": query_id}
        if data is not None:
            ensure_widget_state(data, what="answer data")
            payload["data"] = data
        await self._request("answerWidgetQuery", payload)

    async def _edit(self, api_method: str, payload: dict[str, object]) -> None:
        try:
            await self._request(api_method, payload)
        except TelegramBadRequest as exc:
            if _NOT_MODIFIED in str(exc).lower():
                return
            raise

    async def _request(self, api_method: str, payload: dict[str, object]) -> Any:
        bot = self._bot
        session = bot.session
        method = _METHOD_TYPES[api_method]()
        url = session.api.api_url(token=bot.token, method=api_method)
        create_session = getattr(session, "create_session", None)
        if not callable(create_session):
            msg = "bot session cannot post widget methods"
            raise RuntimeError(msg)
        http = await create_session()
        body = {key: value for key, value in payload.items() if value is not None}
        try:
            async with http.post(url, json=body, timeout=session.timeout) as resp:
                raw = await resp.text()
                status = resp.status
        except TimeoutError as exc:
            raise TelegramNetworkError(method=method, message="Request timeout error") from exc
        except ClientError as exc:
            raise TelegramNetworkError(method=method, message=f"{type(exc).__name__}: {exc}") from exc
        response = session.check_response(bot=bot, method=method, status_code=status, content=raw)
        return response.result


def _media_source(file_id: str | None, path: str | None) -> str | FSInputFile:
    if file_id:
        return file_id
    if path:
        return FSInputFile(path=path)
    msg = "companion media needs a file_id or a path"
    raise ValueError(msg)


class AiogramCompanionMedia:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def upsert(
        self,
        chat_id: int,
        *,
        message_id: int | None,
        kind: str,
        file_id: str | None,
        path: str | None,
        cover_file_id: str | None,
        caption: str,
    ) -> int:
        source = _media_source(file_id, path)
        media_kind = kind.strip().lower()
        if message_id is None:
            return await self._send(chat_id, media_kind, source, cover_file_id, caption, path)
        return await self._edit(chat_id, message_id, media_kind, source, cover_file_id, caption, path)

    async def _send(
        self,
        chat_id: int,
        kind: str,
        source: str | FSInputFile,
        cover_file_id: str | None,
        caption: str,
        path: str | None,
    ) -> int:
        if kind == "photo":
            sent = await self._bot.send_photo(chat_id, source, caption=caption, parse_mode=None)
            _remember_photo_cover(path, sent)
            return sent.message_id
        if kind == "video":
            sent = await self._bot.send_video(
                chat_id,
                source,
                caption=caption,
                parse_mode=None,
                cover=cover_file_id,
                supports_streaming=True,
            )
            return sent.message_id
        msg = f"companion media kind must be photo or video, got {kind!r}"
        raise ValueError(msg)

    async def _edit(
        self,
        chat_id: int,
        message_id: int,
        kind: str,
        source: str | FSInputFile,
        cover_file_id: str | None,
        caption: str,
        path: str | None,
    ) -> int:
        if kind == "photo":
            media = InputMediaPhoto(media=source, caption=caption, parse_mode=None)
        elif kind == "video":
            media = InputMediaVideo(
                media=source,
                caption=caption,
                parse_mode=None,
                cover=cover_file_id,
                supports_streaming=True,
            )
        else:
            msg = f"companion media kind must be photo or video, got {kind!r}"
            raise ValueError(msg)
        edited = await self._bot.edit_message_media(media=media, chat_id=chat_id, message_id=message_id)
        if isinstance(edited, bool):
            return message_id
        if kind == "photo":
            _remember_photo_cover(path, edited)
        return int(edited.message_id)


def _remember_photo_cover(path: str | None, sent: object) -> None:
    if not path:
        return
    photo = getattr(sent, "photo", None)
    if not photo:
        return
    file_id = getattr(photo[-1], "file_id", None)
    if isinstance(file_id, str) and file_id:
        remember_glyph_cover(path, file_id)
