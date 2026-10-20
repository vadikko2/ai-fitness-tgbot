"""Leaving a screen deletes that screen's messages. Editing a card does not."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from fitness_bot.domain.enums import ExpectedInput, ProgramType, SessionStatus
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay, WorkoutDocument
from fitness_bot.presentation.chat_pages import (
    DELETE_PAUSE_SECONDS,
    ChatPageMiddleware,
    bind_bot,
    dismiss_pushes,
    page_message_ids,
    push_message_ids,
    push_scope,
    remember,
    remember_incoming,
    reset_chat_pages,
)
from fitness_bot.presentation.routers.body import create_body_router
from fitness_bot.presentation.routers.progress_photo import create_progress_photo_router
from fitness_bot.presentation.routers.session import (
    create_session_router,
    handle_slot_weight_utterance,
)
from fitness_bot.presentation.templates_env import create_jinja_env
from fitness_bot.service.models.commands.body import CancelProgressPhotoCaptureCommand
from fitness_bot.service.models.commands.session import FinalizeSessionCommand, FinalizeSessionCommandResult
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.match_exercises import (
    GetExerciseGuideQuery,
    GetExerciseGuideResult,
    GetExerciseNamesQuery,
    GetExerciseNamesResult,
)
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery, GetTodayWorkoutQueryResult
from fitness_bot.service.models.queries.users import GetWorkflowQuery, GetWorkflowQueryResult


class _User:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _Chat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class _Sent:
    def __init__(self, message_id: int, chat_id: int) -> None:
        self.message_id = message_id
        self.chat = _Chat(chat_id)


class _Bot:
    def __init__(self) -> None:
        self.deleted: list[int] = []
        self.edits: list[int] = []

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append(message_id)

    async def edit_message_text(self, text: str, *, chat_id: int, message_id: int, **kwargs: object) -> None:
        self.edits.append(message_id)


class _Outgoing:
    def __init__(self, bot: _Bot, *, chat_id: int, user_id: int, start_id: int) -> None:
        self.bot = bot
        self.chat = _Chat(chat_id)
        self.from_user = _User(user_id)
        self.message_id = start_id
        self._next = start_id
        self.answers: list[str] = []

    async def answer(self, text: str, reply_markup=None, **kwargs: object) -> _Sent:
        self.answers.append(text)
        self._next += 1
        return _Sent(self._next, self.chat.id)


class _Callback:
    def __init__(self, data: str, message: _Outgoing, bot: _Bot) -> None:
        self.data = data
        self.message = message
        self.bot = bot
        self.from_user = message.from_user
        self.answered = 0

    async def answer(self, *args: object, **kwargs: object) -> None:
        self.answered += 1


class _Card:
    def __init__(self, bot: _Bot) -> None:
        self.bot = bot
        self.chat = _Chat(9)
        self.message_id = 15
        self.from_user = _User(7)
        self.answers: list[str] = []
        self.edits: list[str] = []

    async def answer(self, text: str, reply_markup=None, **kwargs: object) -> None:
        self.answers.append(text)

    async def edit_text(self, text: str, reply_markup=None, **kwargs: object) -> None:
        self.edits.append(text)


def _handler(router, name: str):
    return next(item.callback for item in router.callback_query.handlers if item.callback.__name__ == name)


class _Pack:
    def __init__(self) -> None:
        self.exercise_id = uuid4()
        self.document = WorkoutDocument(
            program_type=ProgramType.FULL_BODY,
            days=[
                WorkoutDay(
                    weekday=1,
                    title="Грудь",
                    position=1,
                    slots=[
                        ExerciseSlot(
                            position=1,
                            exercise_id=self.exercise_id,
                            sets=3,
                            reps=8,
                            rest_seconds=90,
                            rpe=7,
                        ),
                    ],
                ),
            ],
        )

    async def send(self, request: object):
        if isinstance(request, GetTodayWorkoutQuery):
            return GetTodayWorkoutQueryResult(
                screen="session",
                document=self.document,
                session_status=SessionStatus.IN_PROGRESS,
            )
        if isinstance(request, GetExerciseNamesQuery):
            return GetExerciseNamesResult(names={str(self.exercise_id): "Жим"}, primary_muscles={})
        if isinstance(request, GetExerciseGuideQuery):
            return GetExerciseGuideResult(found=False)
        if isinstance(request, FinalizeSessionCommand):
            return FinalizeSessionCommandResult(
                session_id=uuid4(),
                document=self.document,
                session_status=SessionStatus.COMPLETED,
            )
        raise AssertionError(type(request))


class _Flow:
    def __init__(self) -> None:
        self.exercise_id = uuid4()
        self.slot = ExerciseSlot(
            position=2,
            exercise_id=self.exercise_id,
            sets=3,
            reps=10,
            weight_kg=Decimal("16"),
            rest_seconds=60,
            rpe=7,
        )
        self.document = WorkoutDocument(
            program_type=ProgramType.FULL_BODY,
            days=[WorkoutDay(weekday=1, title="Грудь", position=1, slots=[self.slot])],
        )
        self.expected_input = ExpectedInput.NONE
        self.expected_field: str | None = None
        self.focus_slot: int | None = None

    async def send(self, request: object):
        if isinstance(request, ExpectInputCommand):
            self.expected_input = request.expected_input
            self.expected_field = request.expected_field
            self.focus_slot = request.focus_slot
            return None
        if isinstance(request, GetWorkflowQuery):
            return GetWorkflowQueryResult(
                user_id=uuid4(),
                chat_id=9,
                expected_input=self.expected_input,
                expected_field=self.expected_field,
                focus_slot=self.focus_slot,
                profile_complete=True,
                goal=None,
            )
        if isinstance(request, GetTodayWorkoutQuery):
            return GetTodayWorkoutQueryResult(
                screen="session",
                document=self.document,
                session_status=SessionStatus.IN_PROGRESS,
            )
        if isinstance(request, GetExerciseNamesQuery):
            return GetExerciseNamesResult(names={str(self.exercise_id): "Жим"}, primary_muscles={})
        if isinstance(request, GetExerciseGuideQuery):
            return GetExerciseGuideResult(found=False)
        raise AssertionError(type(request))


async def _dispatch(callback: _Callback, handler) -> None:
    async def run(event: _Callback, data: dict) -> None:
        await handler(event)

    await ChatPageMiddleware()(run, callback, {})


async def test_leaving_a_page_deletes_that_page_and_keeps_the_new_one() -> None:
    reset_chat_pages()
    user_id = 21
    chat_id = 21
    reply = _Outgoing(_Bot(), chat_id=chat_id, user_id=user_id, start_id=12)
    reply.message_id = 12
    remember_incoming(reply)
    remember(user_id, chat_id, 10)
    remember(user_id, chat_id, 11)
    previous = [12, 10, 11]

    pack = _Pack()
    router = create_session_router(jinja_env=create_jinja_env(), mediator=pack)  # type: ignore[arg-type]
    bot = _Bot()
    menu = _Outgoing(bot, chat_id=chat_id, user_id=user_id, start_id=100)
    opened = _Callback("sess", menu, bot)
    pauses: list[float] = []

    async def _sleep(seconds: float) -> None:
        pauses.append(seconds)

    with (
        patch("fitness_bot.presentation.chat_pages.asyncio.sleep", _sleep),
        patch("fitness_bot.presentation.planned_day_pack.asyncio.sleep", _sleep),
    ):
        await _dispatch(opened, _handler(router, "handle_sess"))

    workout_ids = page_message_ids(user_id)
    assert opened.answered == 1
    assert bot.deleted == previous
    assert workout_ids
    assert set(workout_ids).isdisjoint(previous)
    assert pauses.count(DELETE_PAUSE_SECONDS) == len(previous) - 1

    done = _Callback("sess_fin", _Outgoing(bot, chat_id=chat_id, user_id=user_id, start_id=200), bot)
    with (
        patch("fitness_bot.presentation.chat_pages.asyncio.sleep", _sleep),
        patch("fitness_bot.presentation.planned_day_pack.asyncio.sleep", _sleep),
    ):
        await _dispatch(done, _handler(router, "handle_sess_fin"))

    completion_ids = page_message_ids(user_id)
    assert done.answered == 1
    assert workout_ids
    assert all(message_id in bot.deleted for message_id in workout_ids)
    assert completion_ids
    assert set(completion_ids).isdisjoint(bot.deleted)
    assert "Тренировка завершена" in done.message.answers[0]
    reset_chat_pages()


async def test_in_place_weight_edit_does_not_delete_the_page() -> None:
    reset_chat_pages()
    remember(7, 9, 10)
    remember(7, 9, 11)
    flow = _Flow()
    router = create_session_router(jinja_env=create_jinja_env(), mediator=flow)  # type: ignore[arg-type]
    bot = _Bot()
    card = _Card(bot)
    callback = _Callback("slot_fact:2", card, bot)  # type: ignore[arg-type]

    await _dispatch(callback, _handler(router, "handle_slot_fact"))

    typed = _Outgoing(bot, chat_id=9, user_id=7, start_id=99)
    typed.message_id = 99
    await handle_slot_weight_utterance(
        mediator=flow,  # type: ignore[arg-type]
        message=typed,  # type: ignore[arg-type]
        text="20",
        focus_slot=2,
    )

    assert bot.deleted == []
    assert card.answers == []
    assert card.edits
    assert typed.answers == []
    assert bot.edits == [15]
    assert page_message_ids(7) == [10, 11, 99]
    reset_chat_pages()


class _PushBot:
    def __init__(self) -> None:
        self.deleted: list[int] = []
        self._next = 0

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> _Sent:
        self._next += 1
        return _Sent(self._next, chat_id)

    async def send_photo(self, chat_id: int, photo: object = None, **kwargs: object) -> _Sent:
        self._next += 1
        return _Sent(self._next, chat_id)

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append(message_id)


async def test_notification_stays_when_another_screen_opens() -> None:
    reset_chat_pages()
    user_id = 21
    bot = _PushBot()
    bind_bot(bot)  # type: ignore[arg-type]
    remember(user_id, user_id, 10)
    with push_scope(user_id):
        training = await bot.send_message(user_id, "Завтра тренировка. Идёшь?")
    with push_scope(user_id, dismiss="weight"):
        weight = await bot.send_message(user_id, "Какой сейчас вес?")

    menu = _Outgoing(bot, chat_id=user_id, user_id=user_id, start_id=100)  # type: ignore[arg-type]
    opened = _Callback("sess", menu, bot)  # type: ignore[arg-type]

    async def show_workout(callback: _Callback) -> None:
        await callback.message.answer("Тренировка")

    await _dispatch(opened, show_workout)

    assert 10 in bot.deleted
    assert training.message_id not in bot.deleted
    assert weight.message_id not in bot.deleted
    assert push_message_ids(user_id) == [training.message_id, weight.message_id]
    assert training.message_id not in page_message_ids(user_id)
    reset_chat_pages()


async def test_notification_is_deleted_only_after_its_button() -> None:
    reset_chat_pages()
    user_id = 21
    bot = _PushBot()
    bind_bot(bot)  # type: ignore[arg-type]
    remember(user_id, user_id, 10)
    with push_scope(user_id):
        training = await bot.send_message(user_id, "Завтра тренировка. Идёшь?")
    with push_scope(user_id, dismiss="weight"):
        weight = await bot.send_message(user_id, "Какой сейчас вес?")

    note = _Outgoing(bot, chat_id=user_id, user_id=user_id, start_id=training.message_id)  # type: ignore[arg-type]
    choice = _Callback("tr_yes:2026-10-20", note, bot)  # type: ignore[arg-type]

    async def choose(callback: _Callback) -> None:
        await callback.message.answer("Ок. Вот черновик")

    await _dispatch(choice, choose)

    assert training.message_id in bot.deleted
    assert weight.message_id not in bot.deleted
    assert 10 not in bot.deleted
    assert push_message_ids(user_id) == [weight.message_id]
    reply_ids = page_message_ids(user_id)
    assert 10 in reply_ids
    assert training.message_id not in reply_ids
    assert "Ок. Вот черновик" in note.answers
    reset_chat_pages()


async def test_weight_notification_is_deleted_when_the_number_is_saved() -> None:
    reset_chat_pages()
    user_id = 21
    bot = _PushBot()
    bind_bot(bot)  # type: ignore[arg-type]
    with push_scope(user_id):
        training = await bot.send_message(user_id, "Завтра тренировка. Идёшь?")
    with push_scope(user_id, dismiss="weight"):
        weight = await bot.send_message(user_id, "Какой сейчас вес?")
        angle = await bot.send_photo(user_id, object())

    await dismiss_pushes(bot, user_id, "weight")

    assert weight.message_id in bot.deleted
    assert angle.message_id in bot.deleted
    assert training.message_id not in bot.deleted
    assert push_message_ids(user_id) == [training.message_id]
    reset_chat_pages()


class _SkipMediator:
    def __init__(self, expected: ExpectedInput) -> None:
        self.expected = expected
        self.sent: list[object] = []

    async def send(self, request: object):
        self.sent.append(request)
        if isinstance(request, GetWorkflowQuery):
            return GetWorkflowQueryResult(
                user_id=uuid4(),
                chat_id=21,
                expected_input=self.expected,
                expected_field=None,
                focus_slot=None,
                profile_complete=True,
                goal=None,
            )
        return None


async def test_skip_deletes_the_reminder_and_leaves_the_open_screen() -> None:
    reset_chat_pages()
    user_id = 21
    bot = _PushBot()
    bind_bot(bot)  # type: ignore[arg-type]
    remember(user_id, user_id, 10)
    with push_scope(user_id, dismiss="weight"):
        weight = await bot.send_message(user_id, "Какой сейчас вес?")

    mediator = _SkipMediator(ExpectedInput.WEIGHT)
    router = create_body_router(jinja_env=create_jinja_env(), mediator=mediator)  # type: ignore[arg-type]
    note = _Outgoing(bot, chat_id=user_id, user_id=user_id, start_id=weight.message_id)  # type: ignore[arg-type]
    choice = _Callback("wt_skip", note, bot)  # type: ignore[arg-type]
    await _dispatch(choice, _handler(router, "handle_wt_skip"))

    assert weight.message_id in bot.deleted
    assert 10 not in bot.deleted
    assert page_message_ids(user_id) == [10]
    assert note.answers == []
    cleared = [item for item in mediator.sent if isinstance(item, ExpectInputCommand)]
    assert len(cleared) == 1
    assert cleared[0].expected_input == ExpectedInput.NONE
    reset_chat_pages()


async def test_photo_skip_cancels_the_ask_without_clearing_the_screen() -> None:
    reset_chat_pages()
    user_id = 21
    bot = _PushBot()
    bind_bot(bot)  # type: ignore[arg-type]
    remember(user_id, user_id, 10)
    with push_scope(user_id, dismiss="progress_photo"):
        intro = await bot.send_message(user_id, "Фото прогресса")
        angle = await bot.send_photo(user_id, object())

    mediator = _SkipMediator(ExpectedInput.PROGRESS_PHOTO)
    router = create_progress_photo_router(jinja_env=create_jinja_env(), mediator=mediator)  # type: ignore[arg-type]
    note = _Outgoing(bot, chat_id=user_id, user_id=user_id, start_id=angle.message_id)  # type: ignore[arg-type]
    choice = _Callback("pp_skip", note, bot)  # type: ignore[arg-type]
    await _dispatch(choice, _handler(router, "handle_pp_skip"))

    assert intro.message_id in bot.deleted
    assert angle.message_id in bot.deleted
    assert 10 not in bot.deleted
    assert page_message_ids(user_id) == [10]
    assert note.answers == []
    assert any(isinstance(item, CancelProgressPhotoCaptureCommand) for item in mediator.sent)
    reset_chat_pages()
