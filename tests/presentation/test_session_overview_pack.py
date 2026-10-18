from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from fitness_bot.domain.enums import ProgramType, SessionStatus
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay, WorkoutDocument
from fitness_bot.presentation.planned_day_pack import EXERCISE_PACK_PAUSE_SECONDS
from fitness_bot.presentation.routers.session import _show_session_card, create_session_router
from fitness_bot.presentation.templates_env import create_jinja_env
from fitness_bot.service.models.commands.session import (
    ConfirmExerciseAsPlannedCommand,
    ConfirmExerciseAsPlannedCommandResult,
    FinalizeSessionCommand,
    FinalizeSessionCommandResult,
)
from fitness_bot.service.models.queries.match_exercises import (
    ExerciseGuideVideoItem,
    GetExerciseGuideQuery,
    GetExerciseGuideResult,
    GetExerciseNamesQuery,
    GetExerciseNamesResult,
)
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery, GetTodayWorkoutQueryResult


def _slot(**kwargs: object) -> ExerciseSlot:
    payload = {"sets": 4, "reps": 8, "rest_seconds": 90, "rpe": 7}
    payload.update(kwargs)
    return ExerciseSlot(**payload)  # type: ignore[arg-type]


def _callbacks(markup) -> list[str]:
    if markup is None:
        return []
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _button_texts(markup) -> list[str]:
    if markup is None:
        return []
    return [button.text for row in markup.inline_keyboard for button in row]


def _exercise_actions(position: int) -> list[str]:
    return [f"slot_plan:{position}", f"slot_fact:{position}", f"slot_alt:{position}"]


_EXERCISE_LABELS = ["✅ Как в плане → дальше", "✏️ Вес и повторы", "🔄 Похожее упражнение"]
_CLOSER_ACTIONS = ["sess_plan_all", "sess_fin", "home"]
_CLOSER_LABELS = ["Выполнить все", "Завершить тренировку", "🏠 В меню"]


class _Message:
    def __init__(self) -> None:
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None, **kwargs: object) -> None:
        self.answers.append((text, reply_markup))


class _User:
    id = 21


class _Callback:
    def __init__(self, data: str, message: _Message) -> None:
        self.data = data
        self.from_user = _User()
        self.message = message
        self.answered = 0

    async def answer(self, *args: object, **kwargs: object) -> None:
        self.answered += 1


def _document() -> tuple[WorkoutDocument, object]:
    exercise_id = uuid4()
    logged_id = uuid4()
    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="Грудь",
                position=1,
                warmup="Суставы <плеч>",
                cooldown="Дыхание <спокойное>",
                slots=[
                    _slot(
                        position=1,
                        exercise_id=logged_id,
                        weight_kg=Decimal("40"),
                        actual=SlotActual(sets=4, reps=8, weight_kg=Decimal("40")),
                    ),
                    _slot(position=2, exercise_id=exercise_id, weight_kg=Decimal("60")),
                ],
            ),
        ],
    )
    return document, exercise_id


class _Mediator:
    def __init__(self, document: WorkoutDocument, exercise_id: object) -> None:
        self.document = document
        self.exercise_id = exercise_id

    async def send(self, request: object):
        if isinstance(request, GetTodayWorkoutQuery):
            return GetTodayWorkoutQueryResult(
                screen="session",
                document=self.document,
                session_status=SessionStatus.IN_PROGRESS,
            )
        if isinstance(request, GetExerciseNamesQuery):
            return GetExerciseNamesResult(
                names={str(self.exercise_id): "Жим <лёжа>"},
                primary_muscles={str(self.exercise_id): ["грудь"]},
            )
        if isinstance(request, GetExerciseGuideQuery):
            if request.exercise_id != self.exercise_id:
                return GetExerciseGuideResult(found=False)
            return GetExerciseGuideResult(
                found=True,
                exercise_id=self.exercise_id,
                name="Жим <лёжа>",
                technique="Лягте на скамью.\n\nНе бросайте гриф.",
                primary_muscles=["грудь"],
                videos=[
                    ExerciseGuideVideoItem(platform="youtube", url="https://youtu.be/abc", title="Жим <демо>"),
                    ExerciseGuideVideoItem(platform="youtube", url="javascript:alert(1)", title="мимо"),
                ],
            )
        raise AssertionError(type(request))


def _handler(router, name: str):
    return next(item.callback for item in router.callback_query.handlers if item.callback.__name__ == name)


async def test_session_pack_is_calm_messages_then_one_next_exercise() -> None:
    document, exercise_id = _document()
    message = _Message()
    sleeps: list[float] = []

    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    with patch("fitness_bot.presentation.planned_day_pack.asyncio.sleep", _sleep):
        await _show_session_card(
            mediator=_Mediator(document, exercise_id),  # type: ignore[arg-type]
            message=message,  # type: ignore[arg-type]
            document=document,
        )

    texts = [text for text, _markup in message.answers]
    assert sleeps == [EXERCISE_PACK_PAUSE_SECONDS] * (len(texts) - 1)
    assert texts[0] == "<b>Разминка</b>\nСуставы &lt;плеч&gt;"
    assert texts[2].split("\n", 1)[0] == "<b>Жим &lt;лёжа&gt;</b>"
    assert "<i>Мышцы:</i> грудь" in texts[2]
    assert "<i>Подходы:</i> 4" in texts[2]
    assert "<blockquote>Лягте на скамью.</blockquote>" in texts[2]
    assert "<blockquote>Не бросайте гриф.</blockquote>" in texts[2]
    assert 'YouTube: <a href="https://youtu.be/abc">Жим &lt;демо&gt;</a>' in texts[2]
    assert "javascript:" not in texts[2]
    assert "мимо" not in texts[2]
    assert "!" not in texts[2]
    assert texts[3] == "<b>Заминка</b>\nДыхание &lt;спокойное&gt;"
    assert texts[4] == "Можно закрыть тренировку."
    assert "Продолжаем" not in "\n".join(texts)
    assert "Записать подход" not in "\n".join(texts)
    assert _callbacks(message.answers[0][1]) == []
    assert _callbacks(message.answers[1][1]) == _exercise_actions(1)
    assert _button_texts(message.answers[1][1]) == _EXERCISE_LABELS
    assert _callbacks(message.answers[2][1]) == _exercise_actions(2)
    assert _callbacks(message.answers[3][1]) == []
    assert _callbacks(message.answers[4][1]) == _CLOSER_ACTIONS
    assert _button_texts(message.answers[4][1]) == _CLOSER_LABELS
    every = [callback for _text, markup in message.answers for callback in _callbacks(markup)]
    labels = [text for _text, markup in message.answers for text in _button_texts(markup)]
    wall = {"sess_edit", "sess_all", "sess_restart", "ihow:sess", "slot:1", "slot:2", "slot_how:1", "slot_how:2"}
    assert wall.isdisjoint(every)
    assert "Как делать" not in " ".join(labels)
    assert "Назад к тренировке" not in " ".join(labels)


async def test_back_to_workout_resends_the_pack() -> None:
    document, exercise_id = _document()
    mediator = _Mediator(document, exercise_id)
    router = create_session_router(jinja_env=create_jinja_env(), mediator=mediator)  # type: ignore[arg-type]
    message = _Message()
    callback = _Callback("sess", message)
    sleeps: list[float] = []

    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    with patch("fitness_bot.presentation.planned_day_pack.asyncio.sleep", _sleep):
        await _handler(router, "handle_sess")(callback)

    assert callback.answered == 1
    assert sleeps[0] == EXERCISE_PACK_PAUSE_SECONDS
    assert message.answers[0][0].startswith("<b>Разминка</b>")
    assert _callbacks(message.answers[2][1]) == _exercise_actions(2)
    assert _callbacks(message.answers[-1][1]) == _CLOSER_ACTIONS


async def test_finished_pack_offers_done_instead_of_an_exercise_wall() -> None:
    exercise_id = uuid4()
    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="Грудь",
                position=1,
                slots=[
                    _slot(
                        position=1,
                        exercise_id=exercise_id,
                        actual=SlotActual(sets=4, reps=8),
                    ),
                ],
            ),
        ],
    )
    message = _Message()

    async def _sleep(seconds: float) -> None:
        return None

    with patch("fitness_bot.presentation.planned_day_pack.asyncio.sleep", _sleep):
        await _show_session_card(
            mediator=_Mediator(document, exercise_id),  # type: ignore[arg-type]
            message=message,  # type: ignore[arg-type]
            document=document,
        )

    assert _callbacks(message.answers[0][1]) == _exercise_actions(1)
    assert _callbacks(message.answers[-1][1]) == _CLOSER_ACTIONS
    assert "slot:" not in " ".join(_callbacks(message.answers[-1][1]))


class _FinishMediator:
    def __init__(self, document: WorkoutDocument, *, fail_confirm: bool = False) -> None:
        self.document = document
        self.fail_confirm = fail_confirm
        self.requests: list[object] = []

    async def send(self, request: object):
        self.requests.append(request)
        if isinstance(request, GetTodayWorkoutQuery):
            return GetTodayWorkoutQueryResult(
                screen="session",
                document=self.document,
                session_status=SessionStatus.IN_PROGRESS,
            )
        if isinstance(request, ConfirmExerciseAsPlannedCommand):
            if self.fail_confirm:
                raise DomainError("open session is required")
            slot = next(
                item for day in self.document.days for item in day.slots if item.position == request.slot_position
            )
            return ConfirmExerciseAsPlannedCommandResult(
                session_id=uuid4(),
                slot=slot,
                document=self.document,
            )
        if isinstance(request, FinalizeSessionCommand):
            return FinalizeSessionCommandResult(
                session_id=uuid4(),
                document=self.document,
                session_status=SessionStatus.COMPLETED,
            )
        if isinstance(request, GetExerciseNamesQuery):
            return GetExerciseNamesResult(names={})
        raise AssertionError(type(request))


async def test_do_all_confirms_only_open_slots_then_finishes() -> None:
    document, _exercise_id = _document()
    mediator = _FinishMediator(document)
    router = create_session_router(jinja_env=create_jinja_env(), mediator=mediator)  # type: ignore[arg-type]
    message = _Message()
    callback = _Callback("sess_plan_all", message)

    await _handler(router, "handle_sess_plan_all")(callback)

    confirmed = [item.slot_position for item in mediator.requests if isinstance(item, ConfirmExerciseAsPlannedCommand)]
    assert confirmed == [2]
    assert any(isinstance(item, FinalizeSessionCommand) for item in mediator.requests)
    assert callback.answered == 1
    assert "Тренировка завершена" in message.answers[-1][0]


async def test_finish_keeps_unlogged_slots_and_does_not_confirm_them() -> None:
    document, _exercise_id = _document()
    mediator = _FinishMediator(document)
    router = create_session_router(jinja_env=create_jinja_env(), mediator=mediator)  # type: ignore[arg-type]
    message = _Message()
    callback = _Callback("sess_fin", message)

    await _handler(router, "handle_sess_fin")(callback)

    assert not any(isinstance(item, ConfirmExerciseAsPlannedCommand) for item in mediator.requests)
    assert any(isinstance(item, FinalizeSessionCommand) for item in mediator.requests)
    text = message.answers[-1][0]
    assert "Тренировка завершена" in text
    assert "без факта" in text


async def test_finish_with_nothing_logged_still_completes() -> None:
    exercise_id = uuid4()
    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="Грудь",
                position=1,
                slots=[_slot(position=1, exercise_id=exercise_id)],
            ),
        ],
    )
    mediator = _FinishMediator(document)
    router = create_session_router(jinja_env=create_jinja_env(), mediator=mediator)  # type: ignore[arg-type]
    message = _Message()

    await _handler(router, "handle_sess_fin")(_Callback("sess_fin", message))

    assert not any(isinstance(item, ConfirmExerciseAsPlannedCommand) for item in mediator.requests)
    assert any(isinstance(item, FinalizeSessionCommand) for item in mediator.requests)
    assert "Тренировка завершена" in message.answers[-1][0]
    assert "без факта" in message.answers[-1][0]


async def test_do_all_stops_when_confirm_fails() -> None:
    document, _exercise_id = _document()
    mediator = _FinishMediator(document, fail_confirm=True)
    router = create_session_router(jinja_env=create_jinja_env(), mediator=mediator)  # type: ignore[arg-type]
    message = _Message()
    callback = _Callback("sess_plan_all", message)

    await _handler(router, "handle_sess_plan_all")(callback)

    assert not any(isinstance(item, FinalizeSessionCommand) for item in mediator.requests)
    assert message.answers[-1][0].startswith("Не удалось отметить")
    assert callback.answered == 1
