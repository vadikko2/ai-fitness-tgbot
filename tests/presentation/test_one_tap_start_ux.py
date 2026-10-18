from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from fitness_bot.domain.enums import ProgramStatus, ProgramType
from fitness_bot.domain.users.user import local_calendar_date
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay
from fitness_bot.domain.workout.program import Program
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.presentation.keyboards import (
    SECTION_INFO_ORIGIN,
    START_WORKOUT_LABEL,
    home_keyboard,
    program_screen_keyboard,
    session_card_keyboard,
    session_done_today_keyboard,
    session_rest_keyboard,
)
from fitness_bot.presentation.planned_day_pack import EXERCISE_PACK_PAUSE_SECONDS
from fitness_bot.presentation.routers.session import start_workout_one_tap
from fitness_bot.presentation.templates_env import create_jinja_env
from fitness_bot.service.handlers.commands.body import RecordWellbeingCommandHandler
from fitness_bot.service.handlers.commands.session import StartTodayWorkoutCommandHandler
from fitness_bot.service.handlers.commands.users import EnsureUserCommandHandler
from fitness_bot.service.handlers.queries.match_exercises import (
    GetExerciseGuideQueryHandler,
    GetExerciseNamesQueryHandler,
)
from fitness_bot.service.handlers.queries.session import GetTodayWorkoutQueryHandler
from fitness_bot.service.models.commands.body import RecordWellbeingCommand
from fitness_bot.service.models.commands.session import StartTodayWorkoutCommand
from fitness_bot.service.models.commands.users import EnsureUserCommand
from fitness_bot.service.models.queries.match_exercises import GetExerciseGuideQuery, GetExerciseNamesQuery
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery
from fitness_bot.service.ports.exercise_catalog import InMemoryExerciseCatalog, record

TG = 21
EX_A = uuid4()
EX_B = uuid4()


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class _Mediator:
    def __init__(self, uow: InMemoryUow, catalog: InMemoryExerciseCatalog) -> None:
        self._handlers = {
            StartTodayWorkoutCommand: StartTodayWorkoutCommandHandler(uow),
            GetTodayWorkoutQuery: GetTodayWorkoutQueryHandler(uow),
            GetExerciseNamesQuery: GetExerciseNamesQueryHandler(catalog),
            GetExerciseGuideQuery: GetExerciseGuideQueryHandler(catalog),
        }

    async def send(self, request):
        return await self._handlers[type(request)].handle(request)


class _Message:
    def __init__(self) -> None:
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None, **_: object) -> None:
        self.answers.append((text, reply_markup))


async def _seed(uow: InMemoryUow, *, weekday: int) -> None:
    await EnsureUserCommandHandler(uow).handle(EnsureUserCommand(telegram_user_id=TG, chat_id=210))
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(TG)
        assert user is not None
        program = Program(
            user_id=user.id,
            program_type=ProgramType.FULL_BODY,
            status=ProgramStatus.ACTIVE,
            days=[
                WorkoutDay(
                    weekday=weekday,
                    title="Грудь и спина",
                    position=1,
                    slots=[
                        ExerciseSlot(position=1, exercise_id=EX_A, sets=3, reps=8, rest_seconds=90, rpe=7),
                        ExerciseSlot(position=2, exercise_id=EX_B, sets=3, reps=10, rest_seconds=90, rpe=7),
                    ],
                ),
            ],
            activated_at=datetime.now(UTC) - timedelta(days=1),
        )
        await repos.programs.add(program)
        user.active_program_id = program.id
        await repos.users.save(user)


def _catalog() -> InMemoryExerciseCatalog:
    return InMemoryExerciseCatalog(
        exercises=[
            record(exercise_id=EX_A, name="Жим лёжа", primary_muscles=["грудь"]),
            record(exercise_id=EX_B, name="Тяга штанги", primary_muscles=["широчайшие"]),
        ],
    )


def test_home_has_single_prominent_start_button() -> None:
    first_row = home_keyboard().inline_keyboard[0]
    assert len(first_row) == 1
    assert first_row[0].text == START_WORKOUT_LABEL
    assert first_row[0].callback_data == "sess_go"
    assert "sess" not in _callbacks(home_keyboard())
    assert SECTION_INFO_ORIGIN["sess_go"] == "session"


def test_day_preview_stays_reachable_from_plan() -> None:
    assert "sess" in _callbacks(program_screen_keyboard(has_pending=False, has_active=True))
    assert "sess" not in _callbacks(program_screen_keyboard(has_pending=False, has_active=False))


def test_rest_and_done_keyboards_offer_nearest_day() -> None:
    rest = _callbacks(session_rest_keyboard(alternative=(3, "Ноги")))
    assert rest[0] == "sess_go_day:3"
    assert "sess_go_day:3" not in _callbacks(session_rest_keyboard())
    done = _callbacks(session_done_today_keyboard(weekday=2, alternative=(5, "Спина")))
    assert done[:2] == ["sess_plan_repeat:2", "sess_go_day:5"]
    assert "prog" in done and "home" in done


def test_session_card_shows_adapt_button_only_with_fresh_wellbeing() -> None:
    assert "feel_adapt_today" not in _callbacks(session_card_keyboard(slots=[(1, "Жим")]))
    assert "feel_adapt_today" in _callbacks(session_card_keyboard(slots=[(1, "Жим")], has_unapplied_wellbeing=True))


async def test_one_tap_sends_exercise_pack_then_one_log_button() -> None:
    uow = InMemoryUow()
    today = local_calendar_date(now=datetime.now(UTC), timezone_offset=None).isoweekday()
    await _seed(uow, weekday=today)
    await RecordWellbeingCommandHandler(uow).handle(RecordWellbeingCommand(telegram_user_id=TG, text="<болит> спина"))
    message = _Message()
    sleeps: list[float] = []

    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    with patch("fitness_bot.presentation.planned_day_pack.asyncio.sleep", _sleep):
        await start_workout_one_tap(
            jinja_env=create_jinja_env(),
            mediator=_Mediator(uow, _catalog()),  # type: ignore[arg-type]
            message=message,  # type: ignore[arg-type]
            telegram_user_id=TG,
        )

    texts = [text for text, _markup in message.answers]
    assert len(texts) == 3
    assert sleeps == [EXERCISE_PACK_PAUSE_SECONDS, EXERCISE_PACK_PAUSE_SECONDS]
    assert texts[0].split("\n", 1)[0] == "<b>Жим лёжа</b>"
    assert texts[1].split("\n", 1)[0] == "<b>Тяга штанги</b>"
    assert "<i>Мышцы:</i> грудь" in texts[0]
    assert "<i>Подходы:</i> 3" in texts[0]
    assert "Тренировка сегодня" not in "\n".join(texts)
    assert "Поехали" not in "\n".join(texts)
    assert "Продолжаем" not in "\n".join(texts)
    assert "&lt;болит&gt; спина" in texts[-1]
    assert _callbacks(message.answers[0][1]) == ["slot_plan:1", "slot_fact:1", "slot_alt:1"]
    assert _callbacks(message.answers[1][1]) == ["slot_plan:2", "slot_fact:2", "slot_alt:2"]
    assert _callbacks(message.answers[-1][1]) == ["sess_plan_all", "sess_fin", "home"]
    labels = [button.text for row in message.answers[-1][1].inline_keyboard for button in row]
    assert labels == ["Выполнить все", "Завершить тренировку", "🏠 В меню"]
    every = [callback for _text, markup in message.answers for callback in _callbacks(markup)]
    forbidden = {"sess_edit", "sess_all", "sess_restart", "ihow:sess", "feel_adapt_today", "slot:1", "slot:2"}
    assert forbidden.isdisjoint(every)


async def test_one_tap_on_rest_day_renders_train_anyway() -> None:
    uow = InMemoryUow()
    today = local_calendar_date(now=datetime.now(UTC), timezone_offset=None).isoweekday()
    other = today % 7 + 1
    await _seed(uow, weekday=other)
    message = _Message()

    await start_workout_one_tap(
        jinja_env=create_jinja_env(),
        mediator=_Mediator(uow, _catalog()),  # type: ignore[arg-type]
        message=message,  # type: ignore[arg-type]
        telegram_user_id=TG,
    )

    text, markup = message.answers[0]
    assert "Грудь и спина" in text
    assert f"sess_go_day:{other}" in _callbacks(markup)
