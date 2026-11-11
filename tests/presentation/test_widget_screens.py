"""Widget screens without Telegram: commands, phases, zlib."""

from __future__ import annotations

import json
import zlib
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fitness_bot.domain.enums import ProfileField, ProgramType, Sex
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay, WorkoutDocument
from fitness_bot.presentation.chat_pages import reset_chat_pages
from fitness_bot.presentation.widgets.frame import (
    WidgetBinding,
    WidgetBindings,
    WidgetFrame,
    WidgetScreenId,
    week_height,
)
from fitness_bot.presentation.widgets.gateway import WidgetGateway, WidgetQuery
from fitness_bot.presentation.widgets.screen import ScreenContext
from fitness_bot.presentation.widgets.screens.console import ConsoleScreen
from fitness_bot.presentation.widgets.screens.home import HomeScreen
from fitness_bot.presentation.widgets.screens.intake import IntakeScreen
from fitness_bot.presentation.widgets.screens.load import load_shells
from fitness_bot.presentation.widgets.screens.menu import MenuScreen
from fitness_bot.presentation.widgets.screens.summary import SummaryScreen
from fitness_bot.presentation.widgets.screens.week import WeekScreen
from fitness_bot.presentation.widgets.state import pack_state
from fitness_bot.service.models.commands.program import (
    ApproveProposalCommand,
    GenerateNextWeekCommand,
    SelectExerciseForProposalCommand,
)
from fitness_bot.service.models.commands.session import (
    ConfirmExerciseAsPlannedCommand,
    FinalizeSessionCommand,
    RecordSlotActualCommand,
    StartSessionFromTemplateCommand,
    StartTodayWorkoutCommand,
)
from fitness_bot.service.models.commands.users import UpdateProfileCommand
from fitness_bot.service.models.queries.match_exercises import (
    GetExerciseGuideQuery,
    GetExerciseNamesQuery,
    MatchExercisesQuery,
)
from fitness_bot.service.models.queries.program import GetPendingProposalQuery
from fitness_bot.service.models.queries.session import (
    GetSessionDetailQuery,
    GetSessionHistoryQuery,
    GetSimilarExercisesQuery,
    GetTodayWorkoutQuery,
)
from fitness_bot.service.models.queries.users import GetHomeQuery, GetHomeQueryResult, GetProfileQuery


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


async def test_console_how_is_text_and_technique_is_a_video_link() -> None:
    screen, mediator, ctx = _console()
    guide = SimpleNamespace(
        technique="Спина ровная, колени в стороны.",
        videos=[
            SimpleNamespace(
                platform="youtube",
                url="https://youtu.be/abcdefghijk",
                title="Тяга штанги в наклоне: техника выполнения",
            ),
        ],
    )
    mediator.replies[GetExerciseGuideQuery] = guide
    frame = await screen.open(ctx)
    how = await screen.apply(_rebind(ctx, frame), "how")
    how_body = json.loads(how.frame.chat_data)
    assert how_body["ph"] == "how"
    assert "колени" in how_body["tip"]
    assert "vids" not in how_body
    video = await screen.apply(_rebind(ctx, frame), "vid")
    video_body = json.loads(video.frame.chat_data)
    assert video.video_file_id is None
    assert video_body["ph"] == "vid"
    assert video_body["vids"][0]["u"] == "https://youtu.be/abcdefghijk"
    assert "техника" in video_body["vids"][0]["t"]
    assert video_body["vids"][0]["p"] == "YouTube"
    assert "tip" not in video_body


_INCLINE_TECHNIQUE = (
    "Поставьте скамью под углом 30–45°, сядьте, стопы на полу, лопатки сведены и прижаты. "
    "Хват чуть шире плеч. Снимите штангу и опускайте к верхней части груди, локти идут слегка ниже плеч, "
    "а не в стороны. Вдох на опускании, выдох на жиме вверх без отрыва поясницы от скамьи. "
    "Ключевое: чем больше угол, тем сильнее работает передняя дельта, поэтому 30–45° — рабочий диапазон. "
    "Частая ошибка — слишком крутой наклон и жим почти как стоя, нагрузка уходит с груди."
)


def _named_console(name: str, technique: str) -> tuple[ConsoleScreen, _Mediator, ScreenContext]:
    exercise_id = uuid4()
    slot = ExerciseSlot(
        position=1,
        exercise_id=exercise_id,
        sets=5,
        reps=5,
        weight_kg=Decimal("65"),
        rest_seconds=180,
        rpe=7,
    )
    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[WorkoutDay(weekday=1, title="Грудь", position=1, slots=[slot])],
    )
    today = SimpleNamespace(document=document, screen="session", technique_video_positions=[], weekday=1)
    mediator = _Mediator(
        {
            GetTodayWorkoutQuery: today,
            GetExerciseNamesQuery: SimpleNamespace(names={str(exercise_id): name}),
            GetExerciseGuideQuery: SimpleNamespace(technique=technique, videos=[]),
        },
    )
    screen = ConsoleScreen(_Shell())
    return screen, mediator, _ctx(mediator, screen=WidgetScreenId.CONSOLE)


async def test_how_shows_the_whole_incline_press_technique() -> None:
    screen, _mediator, ctx = _named_console("Жим штанги лёжа на наклонной скамье", _INCLINE_TECHNIQUE)
    frame = await screen.open(ctx)
    how = await screen.apply(_rebind(ctx, frame), "how")
    body = json.loads(how.frame.chat_data)
    assert body["tip"] == _INCLINE_TECHNIQUE
    assert len(how.frame.chat_data.encode()) <= 1024


async def test_how_clips_a_technique_on_a_sentence_when_the_card_is_full() -> None:
    sentence = "Держите лопатки сведёнными и не отрывайте стопы. "
    screen, _mediator, ctx = _named_console("Ж" * 48, sentence * 40)
    frame = await screen.open(ctx)
    how = await screen.apply(_rebind(ctx, frame), "how")
    body = json.loads(how.frame.chat_data)
    assert len(how.frame.chat_data.encode()) <= 1024
    assert len(body["tip"]) < len(sentence * 40)
    assert body["tip"].endswith(".")


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


async def test_home_open_rest_day_offers_another_program_day() -> None:
    today = SimpleNamespace(
        screen="rest",
        document=None,
        weekday=4,
        completed_weekdays=[],
        planned_weekdays=[1, 3, 5],
        completed_today=False,
        alternative_weekday=5,
        alternative_title="База и акцент на ноги",
    )
    frame = await HomeScreen(_Shell(shell_id="home")).open(
        _ctx(_Mediator({GetTodayWorkoutQuery: today}), screen=WidgetScreenId.HOME),
    )
    body = json.loads(frame.chat_data)
    assert body["mode"] == "rest"
    assert body["altDay"] == 5
    assert "База" in body["alt"]


async def test_home_open_rest_day_falls_back_to_planned_weekdays() -> None:
    today = SimpleNamespace(
        screen="rest",
        document=None,
        weekday=4,
        completed_weekdays=[1],
        planned_weekdays=[1, 3, 5],
        completed_today=False,
        alternative_weekday=None,
        alternative_title=None,
    )
    frame = await HomeScreen(_Shell(shell_id="home")).open(
        _ctx(_Mediator({GetTodayWorkoutQuery: today}), screen=WidgetScreenId.HOME),
    )
    body = json.loads(frame.chat_data)
    assert body["mode"] == "rest"
    assert body["altDay"] == 5
    assert body["cta"] == body["alt"]


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


async def test_home_menu_navigates_to_main_menu_widget() -> None:
    screen = HomeScreen(_Shell(shell_id="home"))
    frame = WidgetFrame(
        screen=WidgetScreenId.HOME,
        chat_data=pack_state({"title": "уже", "mode": "again", "day": 3}),
        caption="",
        shell_id="home",
    )
    result = await screen.apply(_rebind(_ctx(_Mediator(), frame, screen=WidgetScreenId.HOME), frame), "menu")
    assert result.navigate is WidgetScreenId.MENU
    assert result.leave_to_menu is False


def _home_query_result(**kwargs: object) -> GetHomeQueryResult:
    base = dict(
        user_id=uuid4(),
        profile_complete=True,
        goal=None,
        age=None,
        weight_kg=None,
    )
    base.update(kwargs)
    return GetHomeQueryResult(**base)  # type: ignore[arg-type]


async def test_menu_shell_fits_telegram_zlib_limit() -> None:
    shell = load_shells()["menu"]
    assert len(zlib.compress(shell.html().encode("utf-8"), 9)) <= 4096


async def test_menu_train_starts_workout_or_opens_live_console() -> None:
    home = _home_query_result()
    today = SimpleNamespace(
        screen="template",
        document=SimpleNamespace(days=[SimpleNamespace(title="Грудь")]),
        weekday=1,
        completed_weekdays=[],
        completed_today=False,
    )
    screen = MenuScreen(_Shell(shell_id="menu"))
    mediator = _Mediator({GetHomeQuery: home, GetTodayWorkoutQuery: today})
    frame = await screen.open(_ctx(mediator, screen=WidgetScreenId.MENU))
    body = json.loads(frame.chat_data)
    assert body["title"] == "Главное"
    assert body["mode"] == "go"
    assert body["workout"] == "Грудь"
    assert body["coach"] == "find"
    assert body["cab"] == "apply"
    starter = _Mediator({StartTodayWorkoutCommand: SimpleNamespace(outcome="started")})
    train = await screen.apply(_rebind(_ctx(starter, frame, screen=WidgetScreenId.MENU), frame), "train")
    assert train.navigate is WidgetScreenId.CONSOLE
    assert any(isinstance(item, StartTodayWorkoutCommand) for item in starter.sent)
    live = WidgetFrame(
        screen=WidgetScreenId.MENU,
        chat_data=pack_state({**body, "mode": "live"}),
        caption="",
        shell_id="menu",
    )
    resumed = await screen.apply(_rebind(_ctx(_Mediator(), live, screen=WidgetScreenId.MENU), live), "train")
    assert resumed.navigate is WidgetScreenId.CONSOLE


async def test_menu_train_on_rest_day_starts_alternative_weekday() -> None:
    screen = MenuScreen(_Shell(shell_id="menu"))
    frame = WidgetFrame(
        screen=WidgetScreenId.MENU,
        chat_data=pack_state(
            {
                "title": "Главное",
                "mode": "rest",
                "altDay": 1,
                "cta": "Пн · База",
            },
        ),
        caption="",
        shell_id="menu",
    )
    mediator = _Mediator({StartTodayWorkoutCommand: SimpleNamespace(outcome="started")})
    result = await screen.apply(_rebind(_ctx(mediator, frame, screen=WidgetScreenId.MENU), frame), "train")
    assert result.navigate is WidgetScreenId.CONSOLE
    command = next(item for item in mediator.sent if isinstance(item, StartTodayWorkoutCommand))
    assert command.weekday == 1


async def test_menu_train_on_rest_day_probes_today_when_alt_missing() -> None:
    screen = MenuScreen(_Shell(shell_id="menu"))
    frame = WidgetFrame(
        screen=WidgetScreenId.MENU,
        chat_data=pack_state({"title": "Главное", "mode": "rest"}),
        caption="",
        shell_id="menu",
    )
    today = SimpleNamespace(
        screen="rest",
        weekday=4,
        planned_weekdays=[1, 5],
        completed_weekdays=[],
        alternative_weekday=1,
        alternative_title="База",
    )
    mediator = _Mediator(
        {
            GetTodayWorkoutQuery: today,
            StartTodayWorkoutCommand: SimpleNamespace(outcome="started"),
        },
    )
    result = await screen.apply(_rebind(_ctx(mediator, frame, screen=WidgetScreenId.MENU), frame), "train")
    assert result.navigate is WidgetScreenId.CONSOLE
    command = next(item for item in mediator.sent if isinstance(item, StartTodayWorkoutCommand))
    assert command.weekday == 1


async def test_menu_profile_and_coach_use_handoff() -> None:
    screen = MenuScreen(_Shell(shell_id="menu"))
    frame = WidgetFrame(
        screen=WidgetScreenId.MENU,
        chat_data=pack_state({"title": "Главное", "mode": "go", "coach": "mine", "cab": "cab", "n": 2}),
        caption="",
        shell_id="menu",
    )
    ctx = _rebind(_ctx(_Mediator(), frame, screen=WidgetScreenId.MENU), frame)
    assert (await screen.apply(ctx, "prof")).handoff == "profile"
    assert (await screen.apply(ctx, "cmine")).handoff == "coach_mine"
    assert (await screen.apply(ctx, "cab")).handoff == "coach_cab"
    assert (await screen.apply(ctx, "mod")).handoff == "mod"


async def test_menu_marks_week_done_and_nweek_opens_week_draft() -> None:
    home = _home_query_result()
    today = SimpleNamespace(
        screen="rest",
        document=None,
        weekday=4,
        completed_weekdays=[1, 3, 5, 6],
        planned_weekdays=[1, 3, 5, 6],
        completed_today=False,
        week_finished=True,
        alternative_weekday=None,
        alternative_title=None,
    )
    screen = MenuScreen(_Shell(shell_id="menu"))
    opened = await screen.open(
        _ctx(_Mediator({GetHomeQuery: home, GetTodayWorkoutQuery: today}), screen=WidgetScreenId.MENU),
    )
    body = json.loads(opened.chat_data)
    assert body["mode"] == "rest"
    assert body["weekDone"] == 1
    assert "cta" not in body
    assert opened.height is not None
    assert opened.height < 440
    full = await screen.open(
        _ctx(
            _Mediator(
                {
                    GetHomeQuery: _home_query_result(show_coach_badge=False, is_moderator=True),
                    GetTodayWorkoutQuery: SimpleNamespace(
                        screen="template",
                        document=SimpleNamespace(days=[SimpleNamespace(title="Грудь")]),
                        weekday=1,
                        completed_weekdays=[1, 3, 5, 6],
                        completed_today=False,
                        week_finished=True,
                    ),
                },
            ),
            screen=WidgetScreenId.MENU,
        ),
    )
    assert full.height is not None
    assert opened.height < full.height <= 520
    draft = _workout()
    mediator = _Mediator(
        {GenerateNextWeekCommand: SimpleNamespace(document=draft, agent_unavailable=False, schema_failed=False)},
    )
    result = await screen.apply(_rebind(_ctx(mediator, opened, screen=WidgetScreenId.MENU), opened), "nweek")
    assert result.navigate is WidgetScreenId.WEEK
    assert any(isinstance(item, GenerateNextWeekCommand) for item in mediator.sent)


async def test_home_rest_week_done_go_starts_next_week() -> None:
    today = SimpleNamespace(
        screen="rest",
        document=None,
        weekday=4,
        completed_weekdays=[1, 3, 5, 6],
        planned_weekdays=[1, 3, 5, 6],
        completed_today=False,
        week_finished=True,
        alternative_weekday=None,
        alternative_title=None,
    )
    screen = HomeScreen(_Shell(shell_id="home"))
    frame = await screen.open(_ctx(_Mediator({GetTodayWorkoutQuery: today}), screen=WidgetScreenId.HOME))
    body = json.loads(frame.chat_data)
    assert body["weekDone"] == 1
    assert body["mode"] == "rest"
    draft = _workout()
    mediator = _Mediator(
        {GenerateNextWeekCommand: SimpleNamespace(document=draft, agent_unavailable=False, schema_failed=False)},
    )
    result = await screen.apply(_rebind(_ctx(mediator, frame, screen=WidgetScreenId.HOME), frame), "go")
    assert result.navigate is WidgetScreenId.WEEK
    assert any(isinstance(item, GenerateNextWeekCommand) for item in mediator.sent)


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


async def test_done_on_a_weighted_set_continues_into_rest() -> None:
    slot = ExerciseSlot(
        position=1,
        exercise_id=uuid4(),
        sets=5,
        reps=5,
        weight_kg=Decimal("50"),
        rest_seconds=180,
        rpe=7,
    )
    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[WorkoutDay(weekday=1, title="Ноги", position=1, slots=[slot])],
    )
    today = SimpleNamespace(document=document, screen="session", technique_video_positions=[], weekday=1)
    mediator = _Mediator({GetTodayWorkoutQuery: today})
    screen = ConsoleScreen(_Shell())
    ctx = _ctx(mediator, screen=WidgetScreenId.CONSOLE)
    frame = await screen.open(ctx)
    done = await screen.apply(_rebind(ctx, frame), "ok")
    body = json.loads(done.frame.chat_data)
    assert body["ph"] == "rest"
    assert body["rest"] == 180
    assert any(isinstance(item, ConfirmExerciseAsPlannedCommand) for item in mediator.sent)


async def test_done_during_rpe_starts_rest_without_another_write() -> None:
    screen, mediator, ctx = _console()
    data = {
        "ph": "rpe",
        "set": 1,
        "sets": 3,
        "i": 1,
        "n": 1,
        "pos": 1,
        "name": "Присед",
        "plan": "3×8 · 90 с",
        "kg": 50,
        "reps": 8,
        "log": 1,
        "rest": 90,
    }
    frame = WidgetFrame(
        screen=WidgetScreenId.CONSOLE,
        chat_data=pack_state(data),
        caption="",
        shell_id="console",
    )
    result = await screen.apply(_rebind(ctx, frame), "ok")
    body = json.loads(result.frame.chat_data)
    assert body["ph"] == "rest"
    assert _writes(mediator) == []


async def test_reopen_leaves_the_effort_step_for_rest() -> None:
    screen, _mediator, ctx = _console()
    data = {
        "ph": "rpe",
        "set": 1,
        "sets": 5,
        "i": 1,
        "n": 1,
        "pos": 1,
        "name": "Жим",
        "plan": "5×5 · 65 кг · 180 с",
        "kg": 65,
        "reps": 5,
        "log": 1,
        "rest": 180,
    }
    frame = WidgetFrame(
        screen=WidgetScreenId.CONSOLE,
        chat_data=pack_state(data),
        caption="",
        shell_id="console",
    )
    opened = await screen.open(_rebind(ctx, frame))
    assert json.loads(opened.chat_data)["ph"] == "rest"


async def test_replace_lists_similar_exercises() -> None:
    screen, mediator, ctx = _console()
    exercise_id = uuid4()
    mediator.replies[GetSimilarExercisesQuery] = SimpleNamespace(
        items=[SimpleNamespace(name="Жим гантелей на наклонной", exercise_id=exercise_id)],
        blocked_reason=None,
    )
    frame = await screen.open(ctx)
    shown = await screen.apply(_rebind(ctx, frame), "alt")
    body = json.loads(shown.frame.chat_data)
    assert body["ph"] == "alt"
    assert body["alts"] == ["Жим гантелей на наклонной"]
    assert "note" not in body


async def test_replace_explains_when_the_exercise_is_already_logged() -> None:
    screen, mediator, ctx = _console()
    mediator.replies[GetSimilarExercisesQuery] = SimpleNamespace(items=[], blocked_reason="logged")
    frame = await screen.open(ctx)
    shown = await screen.apply(_rebind(ctx, frame), "alt")
    body = json.loads(shown.frame.chat_data)
    assert body["ph"] == "alt"
    assert body["alts"] == []
    assert "заменить нельзя" in body["note"]


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


async def test_console_work_state_includes_workout_progress_pct() -> None:
    screen, _mediator, ctx = _console()
    frame = await screen.open(ctx)
    body = json.loads(frame.chat_data)
    assert body["ph"] == "work"
    assert body["pct"] == 0
    assert body["n"] >= 1
    assert body["ts"] >= 1


async def test_console_progress_rises_after_each_set() -> None:
    slot = ExerciseSlot(
        position=1,
        exercise_id=uuid4(),
        sets=5,
        reps=5,
        weight_kg=Decimal("50"),
        rest_seconds=90,
        rpe=7,
    )
    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[WorkoutDay(weekday=1, title="Ноги", position=1, slots=[slot])],
    )
    today = SimpleNamespace(document=document, screen="session", technique_video_positions=[], weekday=1)
    mediator = _Mediator({GetTodayWorkoutQuery: today})
    screen = ConsoleScreen(_Shell())
    ctx = _ctx(mediator, screen=WidgetScreenId.CONSOLE)
    frame = await screen.open(ctx)
    assert json.loads(frame.chat_data)["pct"] == 0

    first = await screen.apply(_rebind(ctx, frame), "ok")
    assert json.loads(first.frame.chat_data)["ph"] == "rest"
    assert json.loads(first.frame.chat_data)["pct"] == 20

    second = await screen.apply(_rebind(ctx, first.frame), "skip")
    assert json.loads(second.frame.chat_data)["ph"] == "work"
    assert json.loads(second.frame.chat_data)["set"] == 2
    assert json.loads(second.frame.chat_data)["pct"] == 20

    third = await screen.apply(_rebind(ctx, second.frame), "ok")
    assert json.loads(third.frame.chat_data)["pct"] == 40
    fourth_rest = await screen.apply(_rebind(ctx, third.frame), "skip")
    fifth = await screen.apply(_rebind(ctx, fourth_rest.frame), "ok")
    assert json.loads(fifth.frame.chat_data)["set"] == 3
    assert json.loads(fifth.frame.chat_data)["pct"] == 60


async def test_console_list_shows_progress_circle_and_statuses() -> None:
    exercise_id = uuid4()
    slot = ExerciseSlot(
        position=1,
        exercise_id=exercise_id,
        sets=5,
        reps=5,
        weight_kg=Decimal("65"),
        rest_seconds=180,
        rpe=7,
        actual=SlotActual(sets=5, reps=5, weight_kg=Decimal("65")),
    )
    next_slot = ExerciseSlot(
        position=2,
        exercise_id=uuid4(),
        sets=4,
        reps=8,
        rest_seconds=90,
        rpe=7,
    )
    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[WorkoutDay(weekday=1, title="Грудь", position=1, slots=[slot, next_slot])],
    )
    today = SimpleNamespace(document=document, screen="session", technique_video_positions=[], weekday=1)
    mediator = _Mediator(
        {
            GetTodayWorkoutQuery: today,
            GetExerciseNamesQuery: SimpleNamespace(
                names={str(exercise_id): "Жим штанги лёжа", str(next_slot.exercise_id): "Разведения"},
            ),
        },
    )
    screen = ConsoleScreen(_Shell())
    ctx = _ctx(mediator, screen=WidgetScreenId.CONSOLE)
    frame = WidgetFrame(
        screen=WidgetScreenId.CONSOLE,
        chat_data=pack_state(
            {
                "ph": "work",
                "i": 2,
                "n": 2,
                "set": 1,
                "sets": 4,
                "name": "Разведения",
                "plan": "4×8 · 90 с",
                "pos": 2,
                "reps": 8,
                "kg": None,
                "rest": 90,
                "log": 1,
            },
        ),
        caption="",
        shell_id="console",
    )
    shown = await screen.apply(_rebind(ctx, frame), "view")
    body = json.loads(shown.frame.chat_data)
    assert body["ph"] == "view"
    assert body["pct"] == 56
    assert body["title"] == "Грудь"
    assert body["rows"][0].startswith("d:")
    assert body["rows"][1].startswith("n:")
    assert shown.navigate is None


async def test_console_end_finalizes_and_returns_to_menu() -> None:
    screen, mediator, ctx = _console()
    frame = await screen.open(ctx)
    ended = await screen.apply(_rebind(ctx, frame), "end")
    assert ended.leave_to_menu is True
    assert ended.menu_note == "Тренировка завершена."
    assert ended.navigate is None
    assert any(isinstance(item, FinalizeSessionCommand) for item in mediator.sent)


async def test_summary_home_returns_to_classic_menu() -> None:
    screen = SummaryScreen(_Shell(shell_id="summary"))
    mediator = _Mediator(
        {
            GetSessionHistoryQuery: SimpleNamespace(items=[]),
            GetTodayWorkoutQuery: SimpleNamespace(document=None),
        },
    )
    frame = WidgetFrame(
        screen=WidgetScreenId.SUMMARY,
        chat_data=pack_state({"title": "Грудь", "rows": ["Жим — 5×5"], "n": 1}),
        caption="",
        shell_id="summary",
    )
    result = await screen.apply(_ctx(mediator, frame, screen=WidgetScreenId.SUMMARY), "home")
    assert result.leave_to_menu is True
    assert result.navigate is None


async def test_summary_lists_exercises_with_sets_and_reps() -> None:
    session_id = uuid4()
    mediator = _Mediator(
        {
            GetSessionHistoryQuery: SimpleNamespace(
                items=[SimpleNamespace(session_id=session_id, title="Грудь")],
            ),
            GetSessionDetailQuery: SimpleNamespace(
                title="Грудь",
                slots=[
                    SimpleNamespace(
                        exercise_name="Жим штанги лёжа на наклонной скамье",
                        custom_request=None,
                        actual=SlotActual(sets=5, reps=5, weight_kg=Decimal("65")),
                    ),
                    SimpleNamespace(
                        exercise_name="Гакк-приседания",
                        custom_request=None,
                        actual=SlotActual(sets=5, reps=5, weight_kg=Decimal("50")),
                    ),
                ],
            ),
        },
    )
    screen = SummaryScreen(_Shell(shell_id="summary"))
    frame = await screen.open(_ctx(mediator, screen=WidgetScreenId.SUMMARY))
    body = json.loads(frame.chat_data)
    assert body["title"] == "Грудь"
    assert body["n"] == 2
    assert body["rows"][0].startswith("Жим штанги")
    assert "5×5" in body["rows"][0]
    assert "4125" not in frame.chat_data
    assert "tonnage" not in body


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


async def test_week_swap_lists_alternatives_then_applies_choice() -> None:
    current_id = uuid4()
    alt_id = uuid4()
    other_id = uuid4()
    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=3,
                title="Силовая",
                position=1,
                slots=[
                    ExerciseSlot(position=1, exercise_id=current_id, sets=5, reps=5, rest_seconds=90, rpe=7),
                    ExerciseSlot(position=2, exercise_id=other_id, sets=5, reps=5, rest_seconds=90, rpe=7),
                ],
            ),
        ],
    )
    matches = SimpleNamespace(
        items=[
            SimpleNamespace(exercise_id=current_id, name="Гакк-приседания", score=9),
            SimpleNamespace(exercise_id=alt_id, name="Жим ногами", score=6),
            SimpleNamespace(exercise_id=uuid4(), name="Разгибания ног", score=4),
        ],
    )
    mediator = _Mediator(
        {
            GetPendingProposalQuery: SimpleNamespace(document=document),
            MatchExercisesQuery: matches,
            GetExerciseNamesQuery: SimpleNamespace(
                names={str(current_id): "Гакк-приседания", str(alt_id): "Жим ногами"},
                primary_muscles={str(current_id): ["quads"]},
            ),
        },
    )
    screen = WeekScreen(_Shell(shell_id="week"))
    frame = WidgetFrame(
        screen=WidgetScreenId.WEEK,
        chat_data=pack_state(
            {
                "day": 0,
                "days": 1,
                "title": "Ср — Силовая",
                "sel": 0,
                "slots": [{"i": 1, "name": "Гакк-приседания", "load": "55кг 5п"}],
                "dp": 1,
            },
        ),
        caption="",
        shell_id="week",
    )
    opened = await screen.apply(_rebind(_ctx(mediator, frame, screen=WidgetScreenId.WEEK), frame), "swap")
    body = json.loads(opened.frame.chat_data)
    assert "Жим ногами" in body["alts"]
    assert str(current_id) not in body["ids"]
    assert body["alts"]
    picked = await screen.apply(_rebind(_ctx(mediator, opened.frame, screen=WidgetScreenId.WEEK), opened.frame), "swap:0")
    assert any(isinstance(item, SelectExerciseForProposalCommand) for item in mediator.sent)
    assert json.loads(picked.frame.chat_data).get("alts") in ([], None)


def test_week_height_grows_with_slots_and_alts() -> None:
    compact = week_height({"slots": [{"name": "Жим", "load": "10п"}], "alts": []})
    taller = week_height(
        {
            "slots": [{"name": f"Упр {index}", "load": "8п"} for index in range(4)],
            "alts": ["Вариант A", "Вариант B", "Вариант C"],
            "more": 6,
            "note": "Пока нельзя",
        },
    )
    assert 320 <= compact < taller <= 700


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
    assert 'data-op="end"' in console
    assert 'data-op="view"' in console
    assert "data-rpe" not in console
    assert "Точно" not in console
    assert 'data-op="kg"' not in console
    assert 'id="pad"' not in console
    assert "Список" not in console
    assert "Тренировка" in console
    assert 'id="gauge"' in console
    assert 'id="prog"' in console
    assert "hue(" in console
    assert "bar.style.background=color" in console
    summary = shells["summary"].html()
    assert "В меню" in summary
    assert summary.index("В меню") < summary.index('id="list"')
    assert "tonnage" not in summary
    assert "d.spark" not in summary
    home = shells["home"].html()
    assert 'data-op="menu"' in home
    assert "В меню" in home
    assert "weekDone" in home
    assert "Новая неделя" in home
    menu = shells["menu"].html()
    assert 'data-op="nweek"' in menu
    assert "Новая неделя" in menu
    week = shells["week"].html()
    assert "черновик" in week.lower()
    assert "Утвердить неделю" in week
    assert "Выбрано" in week
    assert "← День" in week
    assert "День →" in week
    assert "Убрать" in week
    assert "Заменить" in week
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
        assert "TIMEOUT" in html and "FAILED" in html, key
        listener = html.split('addEventListener("click"', 1)[1]
        assert listener.index("TelegramWidget.request") < listener.index(".then"), key
