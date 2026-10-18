from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from fitness_bot.domain.enums import ProgramType, SessionStatus
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay, WorkoutDocument
from fitness_bot.presentation.planned_day_pack import EXERCISE_PACK_PAUSE_SECONDS
from fitness_bot.presentation.routers.session import _show_session_card, create_session_router
from fitness_bot.presentation.templates_env import create_jinja_env
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
    assert "<b>Жим &lt;лёжа&gt;</b>" in texts[2]
    assert "Лягте на скамью." in texts[2]
    assert "Не бросайте гриф." in texts[2]
    assert '<a href="https://youtu.be/abc">YouTube: Жим &lt;демо&gt;</a>' in texts[2]
    assert "javascript:" not in texts[2]
    assert "мимо" not in texts[2]
    assert "!" not in texts[2]
    assert texts[3] == "<b>Заминка</b>\nДыхание &lt;спокойное&gt;"
    assert texts[4] == "Записать подход"
    assert _callbacks(message.answers[-1][1]) == [f"slot:{2}", "home"]
    assert message.answers[-1][1].inline_keyboard[0][0].text == "Жим <лёжа>"
    earlier = [callback for _text, markup in message.answers[:-1] for callback in _callbacks(markup)]
    assert earlier == []
    wall = {"sess_edit", "sess_all", "sess_restart", "ihow:sess", "slot:1"}
    assert wall.isdisjoint(_callbacks(message.answers[-1][1]))


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
    assert _callbacks(message.answers[-1][1]) == ["slot:2", "home"]


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

    assert _callbacks(message.answers[-1][1]) == ["sess_fin", "home"]
    assert "slot:" not in " ".join(_callbacks(message.answers[-1][1]))
