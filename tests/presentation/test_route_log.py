import io
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update, User

from fitness_bot.presentation.route_log import (
    RouteContextFilter,
    configure_logging,
    install_update_route_logging,
    route_acronym,
    telegram_login,
    telegram_route,
)


def _user(*, user_id: int = 7, username: str | None = "vadim") -> User:
    return User(id=user_id, is_bot=False, first_name="V", username=username)


def _message(**overrides: object) -> Message:
    fields: dict[str, object] = {
        "message_id": 1,
        "date": datetime.now(UTC),
        "chat": Chat(id=1, type="private"),
        "from_user": _user(),
    }
    fields.update(overrides)
    return Message(**fields)  # type: ignore[arg-type]


def test_callback_route_is_acronym_before_colon() -> None:
    update = Update(
        update_id=1,
        callback_query=CallbackQuery(
            id="c",
            from_user=_user(),
            chat_instance="x",
            data="mod_c_ok:55",
        ),
    )
    assert telegram_login(update) == "@vadim"
    assert route_acronym(update) == "mod_c_ok"


def test_command_route_drops_bot_mention_and_payload() -> None:
    update = Update(update_id=2, message=_message(text="/start@FitBot c_abc"))
    assert route_acronym(update) == "start"


def test_plain_text_and_photo_routes() -> None:
    text_update = Update(update_id=3, message=_message(text="привет"))
    photo = _message(
        from_user=_user(user_id=9, username=None),
        photo=[PhotoSize(file_id="f", file_unique_id="u", width=1, height=1)],
    )
    photo_update = Update(update_id=4, message=photo)
    assert route_acronym(text_update) == "text"
    assert route_acronym(photo_update) == "photo"
    assert telegram_login(photo_update) == "id:9"


def test_log_line_includes_login_and_route_only_inside_context() -> None:
    with _captured("fitness_bot.test_route_log") as stream:
        log = logging.getLogger("fitness_bot.test_route_log")
        with telegram_route(login="@vadim", route="sess"):
            log.info("Update id=1 is handled. Duration 10 ms by bot id=2")
        log.info("Start polling")
        text = stream.getvalue()
    assert "INFO:fitness_bot.test_route_log:[@vadim sess] Update id=1 is handled." in text
    assert "INFO:fitness_bot.test_route_log:Start polling" in text
    assert "[@vadim sess] Start polling" not in text


async def test_installed_wrapper_prefixes_logs_for_the_update() -> None:
    class Dummy:
        async def feed_update(self, bot: object, update: Update, **kwargs: object) -> str:
            logging.getLogger("aiogram.event").info("Update id=%s is handled.", update.update_id)
            return "ok"

    dispatcher = Dummy()
    install_update_route_logging(dispatcher)  # type: ignore[arg-type]
    update = Update(
        update_id=8,
        callback_query=CallbackQuery(id="c", from_user=_user(), chat_instance="x", data="sess_plan"),
    )
    with _captured("aiogram.event") as stream:
        result = await dispatcher.feed_update(None, update)
        logging.getLogger("aiogram.event").info("after")
        text = stream.getvalue()

    assert result == "ok"
    assert "[@vadim sess_plan] Update id=8 is handled." in text
    assert "after" in text
    assert "[@vadim sess_plan] after" not in text


def test_configure_logging_prefixes_root_logger(capsys) -> None:
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    old_level = root.level
    try:
        configure_logging()
        assert any(isinstance(item, RouteContextFilter) for handler in root.handlers for item in handler.filters)
        with telegram_route(login="@vadim", route="home"):
            logging.getLogger("fitness_bot.route_log_config").info("Update id=3 is handled.")
        assert "[@vadim home] Update id=3 is handled." in capsys.readouterr().err
    finally:
        root.handlers = old_handlers
        root.setLevel(old_level)


@contextmanager
def _captured(*names: str) -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(tg_ctx)s%(message)s"))
    handler.addFilter(RouteContextFilter())
    saved: list[tuple[logging.Logger, list[logging.Handler], bool, int]] = []
    for name in names:
        log = logging.getLogger(name)
        saved.append((log, list(log.handlers), log.propagate, log.level))
        log.handlers = [handler]
        log.propagate = False
        log.setLevel(logging.INFO)
    try:
        yield stream
    finally:
        for log, handlers, propagate, level in saved:
            log.handlers = handlers
            log.propagate = propagate
            log.setLevel(level)
