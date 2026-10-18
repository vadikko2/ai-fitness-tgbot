from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
from fitness_bot.presentation.routers.session import start_workout_one_tap
from fitness_bot.presentation.templates_env import create_jinja_env
from fitness_bot.service.handlers.commands.body import RecordWellbeingCommandHandler
from fitness_bot.service.handlers.commands.session import StartTodayWorkoutCommandHandler
from fitness_bot.service.handlers.commands.users import EnsureUserCommandHandler
from fitness_bot.service.handlers.queries.match_exercises import GetExerciseNamesQueryHandler
from fitness_bot.service.handlers.queries.session import GetTodayWorkoutQueryHandler
from fitness_bot.service.models.commands.body import RecordWellbeingCommand
from fitness_bot.service.models.commands.session import StartTodayWorkoutCommand
from fitness_bot.service.models.commands.users import EnsureUserCommand
from fitness_bot.service.models.queries.match_exercises import GetExerciseNamesQuery
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


async def test_one_tap_shows_card_and_first_exercise_with_wellbeing_banner() -> None:
    uow = InMemoryUow()
    today = local_calendar_date(now=datetime.now(UTC), timezone_offset=None).isoweekday()
    await _seed(uow, weekday=today)
    await RecordWellbeingCommandHandler(uow).handle(RecordWellbeingCommand(telegram_user_id=TG, text="<болит> спина"))
    message = _Message()

    await start_workout_one_tap(
        jinja_env=create_jinja_env(),
        mediator=_Mediator(uow, _catalog()),  # type: ignore[arg-type]
        message=message,  # type: ignore[arg-type]
        telegram_user_id=TG,
    )

    assert len(message.answers) == 2
    card_text, card_markup = message.answers[0]
    assert "Поехали" in card_text
    assert "&lt;болит&gt; спина" in card_text
    assert "feel_adapt_today" in _callbacks(card_markup)
    slot_text, slot_markup = message.answers[1]
    assert "Жим лёжа" in slot_text
    assert "slot_plan:1" in _callbacks(slot_markup)


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
