"""Widget platform without Telegram: limits, opcodes, bindings, gateway order, chat page."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Chat, Message, Update, User

from fitness_bot.domain.enums import ExpectedInput
from fitness_bot.presentation.chat_pages import (
    ChatPageMiddleware,
    bind_bot,
    page_message_ids,
    remember,
    reset_chat_pages,
)
from fitness_bot.presentation.routers.widget import (
    create_widget_router,
    extract_widget_query,
    polling_allowed_updates,
)
from fitness_bot.presentation.widgets.frame import WidgetBinding, WidgetBindings, WidgetFrame, WidgetScreenId
from fitness_bot.presentation.widgets.gateway import (
    BAD_WIDGET_ANSWER,
    WidgetGateway,
    WidgetQuery,
    install_widget_gateway,
    widget_gateway,
)
from fitness_bot.presentation.widgets.limits import WidgetLimitError
from fitness_bot.presentation.widgets.opcodes import Opcode, OpcodeRejection, parse_opcode
from fitness_bot.presentation.widgets.screen import ScreenContext, ScreenResult
from fitness_bot.presentation.widgets.shell import load_widget_shell
from fitness_bot.presentation.widgets.transport import (
    AiogramCompanionMedia,
    AiogramWidgetTransport,
    _EditWidgetData,
)
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.shared.settings import Settings


class _Flags:
    def __init__(self, enabled: bool = True) -> None:
        self.widgets_enabled = enabled


class _Mediator:
    def __init__(self) -> None:
        self.sent: list[object] = []

    async def send(self, request: object) -> None:
        self.sent.append(request)


class _Transport:
    def __init__(self, calls: list[tuple[object, ...]]) -> None:
        self.calls = calls
        self.fail: Exception | None = None

    async def send(self, chat_id: int, *, html: str, chat_data: str, caption: str, height: int) -> int:
        self.calls.append(("send", chat_id, html, chat_data, caption, height))
        if self.fail is not None:
            raise self.fail
        return 15

    async def edit_state(self, chat_id: int, message_id: int, chat_data: str) -> None:
        self.calls.append(("edit_state", chat_id, message_id, chat_data))

    async def edit_caption(self, chat_id: int, message_id: int, caption: str) -> None:
        self.calls.append(("edit_caption", chat_id, message_id, caption))

    async def answer(self, query_id: str, data: str | None) -> None:
        self.calls.append(("answer", query_id, data))


class _Media:
    def __init__(self, calls: list[tuple[object, ...]]) -> None:
        self.calls = calls

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
        self.calls.append(("media", kind, file_id, cover_file_id, message_id, caption))
        return 50


class _Shell:
    shell_id = "console"

    def html(self) -> str:
        return "<b>ok</b>"


def _frame(caption: str, chat_data: str) -> WidgetFrame:
    return WidgetFrame(
        screen=WidgetScreenId.CONSOLE,
        chat_data=chat_data,
        caption=caption,
        shell_id="console",
    )


class _Screen:
    screen_id = WidgetScreenId.CONSOLE
    shell = _Shell()

    def __init__(self, calls: list[tuple[object, ...]]) -> None:
        self.calls = calls
        self.opened = 0
        self.pending: list[ScreenResult] = []

    async def open(self, ctx: ScreenContext) -> WidgetFrame:
        self.opened += 1
        return _frame("work", '{"ph":"work"}')

    async def apply(self, ctx: ScreenContext, opcode: str) -> ScreenResult:
        self.calls.append(("apply", opcode))
        return self.pending.pop(0)


class _DeleteBot:
    def __init__(self) -> None:
        self.deleted: list[int] = []

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append(message_id)


def _gateway(
    calls: list[tuple[object, ...]],
    *,
    enabled: bool = True,
    bot: object | None = None,
) -> tuple[WidgetGateway, _Transport, _Screen, _Mediator]:
    transport = _Transport(calls)
    screen = _Screen(calls)
    mediator = _Mediator()
    gateway = WidgetGateway(
        transport=transport,
        media=_Media(calls),
        bindings=WidgetBindings(),
        mediator=mediator,  # type: ignore[arg-type]
        settings=_Flags(enabled),
        bot=bot,
    )
    gateway.register_screen(screen)
    return gateway, transport, screen, mediator


def _query(data: str, *, user_id: int = 7, message_id: int = 15) -> WidgetQuery:
    return WidgetQuery(query_id="q1", user_id=user_id, chat_id=7, message_id=message_id, data=data)


class _RecordingTransport(AiogramWidgetTransport):
    def __init__(self) -> None:
        super().__init__(bot=object())  # type: ignore[arg-type]
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def _request(self, api_method: str, payload: dict[str, object]) -> object:
        self.calls.append((api_method, payload))
        if api_method == "sendWidget":
            return {"message_id": 9}
        return True


class _NotModifiedTransport(AiogramWidgetTransport):
    def __init__(self) -> None:
        super().__init__(bot=object())  # type: ignore[arg-type]

    async def _request(self, api_method: str, payload: dict[str, object]) -> object:
        raise TelegramBadRequest(method=_EditWidgetData(), message="Bad Request: message is not modified")


def test_widgets_enabled_defaults_on() -> None:
    assert Settings.model_fields["widgets_enabled"].default is True


def test_zlib_gate_refuses_nul_and_oversized_html(tmp_path: Path) -> None:
    nul = tmp_path / "nul.html"
    nul.write_text("<b>a\x00b</b>", encoding="utf-8")
    with pytest.raises(WidgetLimitError, match="NUL"):
        load_widget_shell("console", nul)

    bulky = tmp_path / "big.html"
    bulky.write_text(os.urandom(4200).hex(), encoding="ascii")
    with pytest.raises(WidgetLimitError, match="zlib"):
        load_widget_shell("console", bulky)

    chrome = tmp_path / "chrome.html"
    chrome.write_text("<!-- note --><header>navy</header>", encoding="utf-8")
    page = tmp_path / "home.html"
    page.write_text("<body>\n<!-- chrome -->\n<p>  home  </p></body>", encoding="utf-8")
    shell = load_widget_shell("home", page, chrome=chrome)
    assert shell.shell_id == "home"
    assert "navy" in shell.html()
    assert "home" in shell.html()
    assert "<!--" not in shell.html()
    assert "  " not in shell.html()


async def test_transport_rejects_limits_and_sends_widget_flags() -> None:
    transport = _RecordingTransport()
    with pytest.raises(WidgetLimitError, match="NUL"):
        await transport.send(1, html="a\x00b", chat_data="{}", caption="c", height=220)
    assert transport.calls == []

    with pytest.raises(WidgetLimitError, match="chat_data"):
        await transport.edit_state(1, 2, "й" * 513)
    assert transport.calls == []

    await transport.edit_state(1, 2, "й" * 512)
    await transport.send(1, html="<b>ok</b>", chat_data="{}", caption="step", height=520)
    await transport.answer("q", None)
    with pytest.raises(WidgetLimitError, match="answer data"):
        await transport.answer("q", "x" * 1025)

    method, payload = transport.calls[1]
    assert method == "sendWidget"
    assert payload["width"] == 0
    assert payload["allow_queries"] is True
    assert payload["is_shared"] is False
    assert payload["height"] == 520
    assert transport.calls[2] == ("answerWidgetQuery", {"widget_query_id": "q"})


async def test_unchanged_widget_edit_is_success() -> None:
    transport = _NotModifiedTransport()
    await transport.edit_state(1, 2, "{}")
    await transport.edit_caption(1, 2, "same")


def test_opcode_grammar() -> None:
    parsed = parse_opcode("rpe:8")
    assert isinstance(parsed, Opcode)
    assert parsed.screen is WidgetScreenId.CONSOLE
    assert parsed.name == "rpe"
    assert parsed.arg == "8"

    samples = {
        "sync": WidgetScreenId.CONSOLE,
        "ok": WidgetScreenId.CONSOLE,
        "w+": WidgetScreenId.CONSOLE,
        "w-": WidgetScreenId.CONSOLE,
        "r+": WidgetScreenId.CONSOLE,
        "r-": WidgetScreenId.CONSOLE,
        "skip": WidgetScreenId.CONSOLE,
        "alt": WidgetScreenId.CONSOLE,
        "alt:2": WidgetScreenId.CONSOLE,
        "back": WidgetScreenId.CONSOLE,
        "how": WidgetScreenId.CONSOLE,
        "vid": WidgetScreenId.CONSOLE,
        "kg": WidgetScreenId.CONSOLE,
        "sum": WidgetScreenId.CONSOLE,
        "pick:goal": WidgetScreenId.INTAKE,
        "inc": WidgetScreenId.INTAKE,
        "dec": WidgetScreenId.INTAKE,
        "preset:45": WidgetScreenId.INTAKE,
        "done": WidgetScreenId.INTAKE,
        "text": WidgetScreenId.INTAKE,
        "day+": WidgetScreenId.WEEK,
        "day-": WidgetScreenId.WEEK,
        "slot:0": WidgetScreenId.WEEK,
        "drop": WidgetScreenId.WEEK,
        "swap": WidgetScreenId.WEEK,
        "swap:1": WidgetScreenId.WEEK,
        "approve": WidgetScreenId.WEEK,
        "go": WidgetScreenId.HOME,
        "home": WidgetScreenId.SUMMARY,
    }
    for raw, screen in samples.items():
        item = parse_opcode(raw)
        assert isinstance(item, Opcode), raw
        assert item.screen is screen
        assert item.raw == raw

    for raw, reason in (
        ("", "empty"),
        ("a" * 65, "size"),
        ("ок", "ascii"),
        ("nope", "unknown"),
        ("rpe:5", "unknown"),
        ("rpe:11", "unknown"),
        ("alt:3", "unknown"),
        ("preset:20", "unknown"),
        ("pick:", "unknown"),
        ("{}", "unknown"),
    ):
        rejected = parse_opcode(raw)
        assert isinstance(rejected, OpcodeRejection)
        assert rejected.reason == reason


def test_bindings_lookup_by_user_and_message() -> None:
    bindings = WidgetBindings()
    binding = WidgetBinding(chat_id=7, message_id=15, screen=WidgetScreenId.CONSOLE)
    bindings.put(4, binding)
    assert bindings.get(4) == binding
    assert bindings.lookup(7, 15) == (4, binding)
    assert bindings.lookup(7, 16) is None
    assert bindings.get(5) is None

    moved = WidgetBinding(chat_id=7, message_id=20, screen=WidgetScreenId.WEEK)
    bindings.put(4, moved)
    assert bindings.lookup(7, 15) is None
    assert bindings.lookup(7, 20) == (4, moved)

    bindings.clear(4)
    assert bindings.get(4) is None
    assert bindings.lookup(7, 20) is None


async def test_gateway_edits_then_answers_and_rejects_a_bad_opcode() -> None:
    reset_chat_pages()
    calls: list[tuple[object, ...]] = []
    bot = _DeleteBot()
    remember(7, 7, 3)
    gateway, _transport, screen, mediator = _gateway(calls, bot=bot)
    opened = await gateway.open(7, WidgetScreenId.CONSOLE, chat_id=7)
    assert opened.use_keyboard is False
    assert opened.message_id == 15
    assert bot.deleted == [3]
    assert page_message_ids(7) == [15]
    assert ("send", 7, "<b>ok</b>", '{"ph":"work"}', "work", 520) in calls

    calls.clear()
    screen.pending.append(
        ScreenResult(
            frame=_frame("rest", '{"ph":"rest"}'),
            answer='{"ph":"rest"}',
            expect=ExpectInputCommand(telegram_user_id=7, expected_input=ExpectedInput.SLOT_WEIGHT),
            video_file_id="vid",
            cover_file_id="glyph",
        ),
    )
    await gateway.on_query(_query("ok"))
    assert [item[0] for item in calls] == [
        "apply",
        "media",
        "edit_state",
        "edit_caption",
        "answer",
    ]
    assert calls[-1] == ("answer", "q1", '{"ph":"rest"}')
    assert calls[1][1:] == ("video", "vid", "glyph", None, "rest")
    assert mediator.sent[0].expected_input is ExpectedInput.SLOT_WEIGHT  # type: ignore[attr-defined]
    assert page_message_ids(7) == [15, 50]
    stored = gateway.bindings.get(7)
    assert stored is not None
    assert stored.frame is not None
    assert stored.frame.caption == "rest"
    assert stored.video_message_id == 50

    calls.clear()
    screen.pending.append(ScreenResult(frame=_frame("rest", '{"ph":"rest"}'), answer='{"ph":"rest"}'))
    await gateway.on_query(_query("sync"))
    assert [item[0] for item in calls] == ["apply", "edit_state", "answer"]

    calls.clear()
    await gateway.on_query(_query("nope"))
    assert calls == [("answer", "q1", BAD_WIDGET_ANSWER)]
    assert screen.pending == []

    calls.clear()
    await gateway.on_query(_query("go"))
    assert calls == [("answer", "q1", BAD_WIDGET_ANSWER)]

    calls.clear()
    await gateway.on_query(_query("ok", message_id=99))
    assert calls == [("answer", "q1", BAD_WIDGET_ANSWER)]
    reset_chat_pages()


async def test_disabled_widgets_ask_the_caller_to_draw_the_keyboard() -> None:
    calls: list[tuple[object, ...]] = []
    gateway, _transport, screen, _mediator = _gateway(calls, enabled=False)
    opened = await gateway.open(7, WidgetScreenId.CONSOLE)
    assert opened.use_keyboard is True
    assert opened.message_id is None
    assert screen.opened == 0
    assert calls == []


async def test_widget_query_reaches_the_gateway() -> None:
    class _Gateway:
        def __init__(self) -> None:
            self.queries: list[WidgetQuery] = []
            self.rejected: list[str] = []

        async def on_query(self, query: WidgetQuery) -> None:
            self.queries.append(query)

        async def reject(self, query_id: str) -> None:
            self.rejected.append(query_id)

    gateway = _Gateway()
    dispatcher = Dispatcher()
    dispatcher.include_router(create_widget_router(gateway=gateway))  # type: ignore[arg-type]
    allowed = polling_allowed_updates(dispatcher)
    assert {"message", "callback_query", "widget_query"} <= set(allowed)

    update = Update.model_validate(
        {
            "update_id": 1,
            "widget_query": {
                "id": "q9",
                "from": {"id": 7, "is_bot": False, "first_name": "A"},
                "chat": {"id": 7, "type": "private"},
                "message_id": 3,
                "chat_instance": "ci",
                "type": {"type": "data"},
                "data": "ok",
            },
        },
    )
    assert update.event_type == "widget_query"
    extracted = extract_widget_query(update.event)
    assert extracted is not None
    assert extracted.data == "ok"

    message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=1, type="private"),
        from_user=User(id=7, is_bot=False, first_name="A"),
    )
    assert Update(update_id=2, message=message).event_type == "message"

    class _Bot:
        id = 1

    await dispatcher.feed_update(_Bot(), update)  # type: ignore[arg-type]
    assert gateway.queries[0].query_id == "q9"
    assert gateway.queries[0].user_id == 7
    assert gateway.rejected == []


def test_widget_gateway_is_installed_for_later_screens() -> None:
    previous = widget_gateway()
    calls: list[tuple[object, ...]] = []
    gateway, _transport, _screen, _mediator = _gateway(calls)
    install_widget_gateway(gateway)
    assert widget_gateway() is gateway
    install_widget_gateway(previous)  # type: ignore[arg-type]


async def test_send_widget_is_tracked_and_edits_do_not_reset_the_page() -> None:
    reset_chat_pages()

    class _Sent:
        def __init__(self, message_id: int, chat_id: int) -> None:
            self.message_id = message_id
            self.chat = type("_Chat", (), {"id": chat_id})()

    class _Bot:
        def __init__(self) -> None:
            self.deleted: list[int] = []
            self.captions: list[str] = []

        async def send_widget(self, chat_id: int, **kwargs: object) -> _Sent:
            return _Sent(40, chat_id)

        async def delete_message(self, chat_id: int, message_id: int) -> None:
            self.deleted.append(message_id)

        async def edit_message_caption(self, **kwargs: object) -> None:
            self.captions.append(str(kwargs.get("caption")))

    class _User:
        def __init__(self, user_id: int) -> None:
            self.id = user_id

    class _Chat:
        def __init__(self, chat_id: int) -> None:
            self.id = chat_id

    class _Outgoing:
        def __init__(self, bot: _Bot) -> None:
            self.bot = bot
            self.chat = _Chat(21)
            self.from_user = _User(21)
            self.message_id = 1
            self._next = 100

        async def answer(self, text: str, reply_markup: object = None, **kwargs: object) -> _Sent:
            self._next += 1
            return _Sent(self._next, self.chat.id)

        async def edit_caption(self, caption: str, **kwargs: object) -> None:
            return None

    class _Callback:
        def __init__(self, data: str, message: _Outgoing, bot: _Bot) -> None:
            self.data = data
            self.message = message
            self.bot = bot
            self.from_user = message.from_user

        async def answer(self, *args: object, **kwargs: object) -> None:
            return None

    bot = _Bot()
    bind_bot(bot)  # type: ignore[arg-type]
    sent = await bot.send_widget(chat_id=21)
    await bot.edit_message_caption(chat_id=21, message_id=sent.message_id, caption="next")
    assert page_message_ids(21) == [40]
    assert bot.deleted == []

    outgoing = _Outgoing(bot)
    callback = _Callback("menu", outgoing, bot)

    async def edit_only(event: _Callback, data: dict[str, object]) -> None:
        await event.message.edit_caption("still here")

    await ChatPageMiddleware()(edit_only, callback, {})
    assert bot.deleted == []
    assert page_message_ids(21) == [40]

    async def open_home(event: _Callback, data: dict[str, object]) -> None:
        await event.message.answer("home")

    await ChatPageMiddleware()(open_home, callback, {})
    assert 40 in bot.deleted
    assert 40 not in page_message_ids(21)
    reset_chat_pages()


async def test_video_companion_passes_cover_and_streaming() -> None:
    class _Bot:
        def __init__(self) -> None:
            self.videos: list[dict[str, object]] = []
            self.edits: list[object] = []

        async def send_video(self, chat_id: int, video: object, **kwargs: object) -> object:
            self.videos.append({"chat_id": chat_id, "video": video, **kwargs})
            return type("_Sent", (), {"message_id": 4})()

        async def edit_message_media(self, *, media: object, chat_id: int, message_id: int) -> object:
            self.edits.append(media)
            return True

    bot = _Bot()
    media = AiogramCompanionMedia(bot)  # type: ignore[arg-type]
    message_id = await media.upsert(
        5,
        message_id=None,
        kind="video",
        file_id="vid",
        path=None,
        cover_file_id="glyph",
        caption="Техника",
    )
    assert message_id == 4
    assert bot.videos[0]["cover"] == "glyph"
    assert bot.videos[0]["supports_streaming"] is True

    edited = await media.upsert(
        5,
        message_id=4,
        kind="photo",
        file_id="pic",
        path=None,
        cover_file_id=None,
        caption="glyph",
    )
    assert edited == 4
    assert bot.edits[0].media == "pic"  # type: ignore[attr-defined]
