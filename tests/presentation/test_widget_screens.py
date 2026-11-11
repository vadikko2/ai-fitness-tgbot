"""Widget screens without Telegram: commands, phases, zlib."""

from __future__ import annotations

import json
import zlib
from types import SimpleNamespace
from uuid import uuid4

from fitness_bot.domain.enums import ProfileField, ProgramType, Sex
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay, WorkoutDocument
from fitness_bot.presentation.chat_pages import reset_chat_pages
from fitness_bot.presentation.widgets.frame import WidgetBinding, WidgetBindings, WidgetFrame, WidgetScreenId
from fitness_bot.presentation.widgets.gateway import WidgetGateway, WidgetQuery
from fitness_bot.presentation.widgets.screen import ScreenContext
from fitness_bot.presentation.widgets.screens.console import ConsoleScreen
from fitness_bot.presentation.widgets.screens.home import HomeScreen
from fitness_bot.presentation.widgets.screens.intake import IntakeScreen
from fitness_bot.presentation.widgets.screens.load import load_shells
from fitness_bot.presentation.widgets.screens.week import WeekScreen
from fitness_bot.presentation.widgets.state import pack_state
from fitness_bot.service.models.commands.program import ApproveProposalCommand
from fitness_bot.service.models.commands.session import (
    ConfirmExerciseAsPlannedCommand,
    RecordSlotActualCommand,
    StartSessionFromTemplateCommand,
    StartTodayWorkoutCommand,
)
from fitness_bot.service.models.commands.users import UpdateProfileCommand
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery
from fitness_bot.service.models.queries.users import GetProfileQuery


class _Shell:
    def __init__(self, html: str = "<b>ok</b>", shell_id: str = "console") -> None:
        self.shell_id = shell_id
        self._html = html

    def html(self) -> str:
        return self._html


class _Mediator:
    def __init__(self, replies: dict[type[object], object] | None = None) -> None:
        self.sent: list[object] = []
        self.replies = replies or {}
        self.profiles: list[object] = []

    async def send(self, request: object) -> object:
        self.sent.append(request)
        if isinstance(request, GetProfileQuery) and self.profiles:
            return self.profiles.pop(0)
        for kind, reply in self.replies.items():
            if isinstance(request, kind):
                return reply
        return SimpleNamespace(
            blocked_empty=False,
            blocked_unresolved=False,
            blocked_schedule=False,
            names={},
            primary_muscles={},
            items=[],
            document=None,
        )


def _ctx(mediator: _Mediator, frame: WidgetFrame | None = None, *, screen: WidgetScreenId) -> ScreenContext:
    return ScreenContext(
        user_id=7,
        binding=WidgetBinding(chat_id=7, message_id=3, screen=screen, frame=frame),
        mediator=mediator,  # type: ignore[arg-type]
    )


def _rebind(ctx: ScreenContext, frame: WidgetFrame) -> ScreenContext:
    return ScreenContext(
        user_id=ctx.user_id,
        binding=WidgetBinding(
            chat_id=ctx.binding.chat_id,
            message_id=ctx.binding.message_id,
            screen=ctx.binding.screen,
            frame=frame,
        ),
        mediator=ctx.mediator,
    )


def _workout() -> WorkoutDocument:
    return WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="Ноги",
                position=1,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=uuid4(),
                        sets=3,
                        reps=8,
                        rest_seconds=90,
                        rpe=7,
                    ),
                ],
            ),
        ],
    )


def _console() -> tuple[ConsoleScreen, _Mediator, ScreenContext]:
    today = SimpleNamespace(document=_workout(), screen="session", technique_video_positions=[], weekday=1)
    mediator = _Mediator({GetTodayWorkoutQuery: today})
    screen = ConsoleScreen(_Shell())
    return screen, mediator, _ctx(mediator, screen=WidgetScreenId.CONSOLE)


def _writes(mediator: _Mediator) -> list[object]:
    return [
        item for item in mediator.sent if isinstance(item, RecordSlotActualCommand | ConfirmExerciseAsPlannedCommand)
    ]


async def test_console_open_and_sync_answer_without_a_companion() -> None:
    reset_chat_pages()
    calls: list[tuple[object, ...]] = []

    class _Transport:
        async def send(self, chat_id: int, *, html: str, chat_data: str, caption: str, height: int) -> int:
            calls.append(("send", chat_id))
            return 15

        async def edit_state(self, chat_id: int, message_id: int, chat_data: str) -> None:
            calls.append(("edit_state", chat_data))

        async def edit_caption(self, chat_id: int, message_id: int, caption: str) -> None:
            calls.append(("edit_caption", caption))

        async def answer(self, query_id: str, data: str | None) -> None:
            calls.append(("answer", query_id, data))

    class _Media:
        async def upsert(self, *args: object, **kwargs: object) -> int:
            calls.append(("media",))
            return 50

    class _Flags:
        widgets_enabled = True

    screen, mediator, _ctx_unused = _console()
    gateway = WidgetGateway(
        transport=_Transport(),  # type: ignore[arg-type]
        media=_Media(),  # type: ignore[arg-type]
        bindings=WidgetBindings(),
        mediator=mediator,  # type: ignore[arg-type]
        settings=_Flags(),
        screens={WidgetScreenId.CONSOLE: screen},
    )
    opened = await gateway.open(7, WidgetScreenId.CONSOLE, chat_id=7)
    assert opened.use_keyboard is False
    assert opened.message_id == 15
    assert not any(item[0] == "media" for item in calls)
    calls.clear()
    await gateway.on_query(WidgetQuery(query_id="q1", user_id=7, chat_id=7, message_id=15, data="sync"))
    assert calls[-1][0] == "answer"
    assert calls[-1][1] == "q1"
    assert isinstance(calls[-1][2], str) and len(calls[-1][2].encode()) <= 1024
    assert not any(item[0] == "media" for item in calls)
    calls.clear()
    await gateway.on_query(WidgetQuery(query_id="q2", user_id=7, chat_id=7, message_id=15, data="ok"))
    assert calls[-1][:2] == ("answer", "q2")
    assert not any(item[0] == "media" for item in calls)
    reset_chat_pages()


async def test_console_technique_stays_inside_the_widget() -> None:
    screen, _mediator, ctx = _console()
    frame = await screen.open(ctx)
    assert "mu" not in json.loads(frame.chat_data)
    result = await screen.apply(_rebind(ctx, frame), "vid")
    assert result.video_file_id is None
    assert result.photo_path is None
    assert json.loads(result.frame.chat_data)["ph"] == "how"


async def test_workout_widgets_send_no_caption_under_the_interface() -> None:
    console, _, ctx = _console()
    opened = await console.open(ctx)
    assert opened.caption == ""
    today = SimpleNamespace(
        screen="template",
        document=SimpleNamespace(days=[SimpleNamespace(title="Грудь")]),
        weekday=3,
        completed_weekdays=[],
    )
    home = await HomeScreen(_Shell(shell_id="home")).open(
        _ctx(_Mediator({GetTodayWorkoutQuery: today}), screen=WidgetScreenId.HOME),
    )
    assert home.caption == ""


async def test_home_go_already_done_answers_without_leaving_the_widget() -> None:
    mediator = _Mediator({StartTodayWorkoutCommand: SimpleNamespace(outcome="already_done")})
    screen = HomeScreen(_Shell(shell_id="home"))
    frame = WidgetFrame(
        screen=WidgetScreenId.HOME,
        chat_data=pack_state({"title": "Низ — квадрицепс", "when": "Ср", "streak": 3}),
        caption="Низ — квадрицепс",
        shell_id="home",
    )
    result = await screen.apply(_rebind(_ctx(mediator, frame, screen=WidgetScreenId.HOME), frame), "go")
    assert result.navigate is None
    assert result.video_file_id is None
    assert result.photo_path is None
    body = json.loads(result.answer or "")
    assert "уже сделана" in str(body["title"])
    assert body["mode"] == "again"


async def test_home_open_completed_today_offers_repeat_and_another_day() -> None:
    today = SimpleNamespace(
        screen="template",
        document=SimpleNamespace(days=[SimpleNamespace(title="Грудь")]),
        weekday=3,
        completed_weekdays=[3],
        completed_today=True,
        alternative_weekday=5,
        alternative_title="Спина",
    )
    mediator = _Mediator({GetTodayWorkoutQuery: today})
    screen = HomeScreen(_Shell(shell_id="home"))
    frame = await screen.open(_ctx(mediator, screen=WidgetScreenId.HOME))
    body = json.loads(frame.chat_data)
    assert body["mode"] == "again"
    assert "уже сделана" in body["title"]
    assert body["day"] == 3
    assert body["altDay"] == 5
    assert "Спина" in body["alt"]


async def test_home_again_overwrites_today_and_opens_the_console() -> None:
    mediator = _Mediator({StartSessionFromTemplateCommand: SimpleNamespace(document=object())})
    screen = HomeScreen(_Shell(shell_id="home"))
    frame = WidgetFrame(
        screen=WidgetScreenId.HOME,
        chat_data=pack_state({"title": "уже", "mode": "again", "day": 3}),
        caption="уже",
        shell_id="home",
    )
    result = await screen.apply(_rebind(_ctx(mediator, frame, screen=WidgetScreenId.HOME), frame), "again")
    assert result.navigate is WidgetScreenId.CONSOLE
    command = next(item for item in mediator.sent if isinstance(item, StartSessionFromTemplateCommand))
    assert command.overwrite_completed is True
    assert command.weekday == 3


async def test_home_other_day_starts_that_weekday_in_the_console() -> None:
    mediator = _Mediator({StartTodayWorkoutCommand: SimpleNamespace(outcome="started")})
    screen = HomeScreen(_Shell(shell_id="home"))
    frame = WidgetFrame(
        screen=WidgetScreenId.HOME,
        chat_data=pack_state({"title": "Выходной", "mode": "rest", "altDay": 5}),
        caption="Выходной",
        shell_id="home",
    )
    result = await screen.apply(_rebind(_ctx(mediator, frame, screen=WidgetScreenId.HOME), frame), "day:5")
    assert result.navigate is WidgetScreenId.CONSOLE
    command = next(item for item in mediator.sent if isinstance(item, StartTodayWorkoutCommand))
    assert command.weekday == 5


async def test_console_ok_records_a_set_and_a_second_ok_in_rest_writes_nothing() -> None:
    screen, mediator, ctx = _console()
    frame = await screen.open(ctx)
    stepped = await screen.apply(_rebind(ctx, frame), "r+")
    assert _writes(mediator) == []
    recorded = await screen.apply(_rebind(ctx, stepped.frame), "ok")
    assert any(isinstance(item, RecordSlotActualCommand) for item in mediator.sent)
    assert json.loads(recorded.frame.chat_data)["ph"] == "rest"
    before = len(mediator.sent)
    again = await screen.apply(_rebind(ctx, recorded.frame), "ok")
    assert len(mediator.sent) == before
    assert json.loads(again.frame.chat_data)["ph"] == "rest"


async def test_console_sync_after_rest_until_advances_the_phase() -> None:
    screen, mediator, ctx = _console()
    data = {
        "ph": "rest",
        "restUntil": 1,
        "set": 1,
        "sets": 3,
        "i": 1,
        "n": 1,
        "pos": 1,
        "name": "Присед",
        "plan": "3×8 · 90 с",
        "kg": None,
        "reps": 8,
        "log": 1,
        "rest": 90,
    }
    frame = WidgetFrame(
        screen=WidgetScreenId.CONSOLE,
        chat_data=pack_state(data),
        caption="Отдых",
        shell_id="console",
    )
    result = await screen.apply(_rebind(ctx, frame), "sync")
    body = json.loads(result.frame.chat_data)
    assert body["ph"] == "work"
    assert body["set"] == 2
    assert _writes(mediator) == []


async def test_intake_pick_sends_update_profile() -> None:
    first = SimpleNamespace(
        profile_complete=False,
        next_field=ProfileField.SEX,
        goal=None,
        sex=None,
        days_per_week=None,
        birth_year=None,
        height_cm=None,
        weight_kg=None,
        body_fat_pct=None,
        session_minutes=None,
    )
    second = SimpleNamespace(
        profile_complete=False,
        next_field=ProfileField.BIRTH_YEAR,
        goal=None,
        sex=Sex.MALE,
        days_per_week=None,
        birth_year=None,
        height_cm=None,
        weight_kg=None,
        body_fat_pct=None,
        session_minutes=None,
    )
    mediator = _Mediator()
    mediator.profiles = [first, second]
    screen = IntakeScreen(_Shell(shell_id="intake"))
    ctx = _ctx(mediator, screen=WidgetScreenId.INTAKE)
    frame = await screen.open(ctx)
    result = await screen.apply(_rebind(ctx, frame), "pick:male")
    updates = [item for item in mediator.sent if isinstance(item, UpdateProfileCommand)]
    assert updates
    assert updates[0].field is ProfileField.SEX
    assert updates[0].value == "male"
    assert json.loads(result.frame.chat_data)["step"] == "birth_year"


async def test_week_approve_sends_approve_proposal() -> None:
    mediator = _Mediator()
    screen = WeekScreen(_Shell(shell_id="week"))
    frame = WidgetFrame(
        screen=WidgetScreenId.WEEK,
        chat_data=pack_state({"day": 0, "title": "Ноги", "slots": [], "sel": 0}),
        caption="Черновик",
        shell_id="week",
    )
    ctx = _ctx(mediator, frame, screen=WidgetScreenId.WEEK)
    result = await screen.apply(ctx, "approve")
    assert any(isinstance(item, ApproveProposalCommand) for item in mediator.sent)
    assert result.navigate is WidgetScreenId.HOME


def test_shell_zlib_stays_within_4096() -> None:
    shells = load_shells()
    sizes = {key: len(zlib.compress(shell.html().encode("utf-8"), 9)) for key, shell in shells.items()}
    assert sizes
    assert all(size <= 4096 for size in sizes.values()), sizes
    console = shells["console"].html()
    assert "data-g=" not in console
    assert "height:140px" not in console
    assert "<footer" not in console
    assert "Готово" in console
    for shell in shells.values():
        html = shell.html()
        assert "<footer" not in html
        assert "data-g=" not in html


def test_shells_request_only_from_a_tap() -> None:
    shells = load_shells()
    for key, shell in shells.items():
        html = shell.html()
        assert "setInterval" not in html, key
        assert html.count("TelegramWidget.request") == 1, key
        assert "answer.result" in html, key
        assert 'code=="TIMEOUT"||code=="FAILED"' in html, key
        listener = html.split('addEventListener("click"', 1)[1]
        assert listener.index("TelegramWidget.request") < listener.index(".then"), key
