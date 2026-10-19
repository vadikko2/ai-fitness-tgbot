from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from fitness_bot.domain.enums import ProgramType
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay, WorkoutDocument
from fitness_bot.presentation.planned_day_pack import (
    EXERCISE_PACK_PAUSE_SECONDS,
    format_planned_exercise_message,
    present_planned_training_day,
)
from fitness_bot.presentation.routers.program import create_program_router
from fitness_bot.presentation.templates_env import create_jinja_env
from fitness_bot.service.models.queries.match_exercises import (
    ExerciseGuideVideoItem,
    GetExerciseGuideQuery,
    GetExerciseGuideResult,
    GetExerciseNamesQuery,
    GetExerciseNamesResult,
)
from fitness_bot.service.models.queries.program import GetActiveProgramQuery, GetActiveProgramQueryResult


def _slot(**kwargs: object) -> ExerciseSlot:
    payload = {"sets": 4, "reps": 8, "rest_seconds": 90, "rpe": 7}
    payload.update(kwargs)
    return ExerciseSlot(**payload)  # type: ignore[arg-type]


def test_exercise_message_shows_catalog_fields_and_escapes() -> None:
    text = format_planned_exercise_message(
        _slot(position=1, exercise_id=uuid4(), weight_kg=Decimal("60")),
        name="Жим <лёжа>",
        technique="Лягте на скамью.\n\nНе бросайте гриф.",
        primary_muscles=["грудь"],
        secondary_muscles=["трицепс", "грудь"],
        videos=[
            ("youtube", "https://youtu.be/abc", "Жим <демо>"),
            ("rutube", "javascript:alert(1)", "мимо"),
        ],
    )
    assert text.split("\n", 1)[0] == "<b>Жим &lt;лёжа&gt;</b>"
    assert "\n\n" not in text
    assert "💪 <b>Мышцы</b>\nгрудь, трицепс" in text
    assert "📋 <b>План</b>\nПовторы: 4 × 8\nВес: 60 кг\nОтдых: 90 с\nУсилие: 7" in text
    assert "✍️ <b>Техника</b>\nЛягте на скамью.\nНе бросайте гриф." in text
    assert '▶️ <b>Видео</b>\nYouTube: <a href="https://youtu.be/abc">Жим &lt;демо&gt;</a>' in text
    assert "<i>" not in text
    assert "<blockquote>" not in text
    assert "<code>" not in text
    assert "<pre>" not in text
    assert "javascript:" not in text
    assert "мимо" not in text


def test_cable_extension_card_is_one_line_between_labeled_rows() -> None:
    text = format_planned_exercise_message(
        _slot(
            position=1,
            exercise_id=uuid4(),
            sets=3,
            reps=12,
            weight_kg=Decimal("20"),
            rest_seconds=60,
            rpe=6,
        ),
        name="Разгибание на блоке с V-рукоятью",
        primary_muscles=["трицепс"],
    )
    assert text == (
        "<b>Разгибание на блоке с V-рукоятью</b>\n"
        "💪 <b>Мышцы</b>\n"
        "трицепс\n"
        "📋 <b>План</b>\n"
        "Повторы: 3 × 12\n"
        "Вес: 20 кг\n"
        "Отдых: 60 с\n"
        "Усилие: 6"
    )
    assert "<blockquote>" not in text
    assert "<i>" not in text
    assert "<code>" not in text
    assert "<pre>" not in text
    assert "Если в каталоге" not in text


def test_exercise_message_shows_fact_only_when_it_differs() -> None:
    planned = _slot(position=1, exercise_id=uuid4(), weight_kg=Decimal("60"))
    same = format_planned_exercise_message(
        planned.model_copy(update={"actual": SlotActual(sets=4, reps=8, weight_kg=Decimal("60"))}),
        name="Жим",
    )
    changed = format_planned_exercise_message(
        planned.model_copy(update={"actual": SlotActual(sets=4, reps=6, weight_kg=Decimal("70"))}),
        name="Жим",
    )
    assert "Факт" not in same
    assert "Мышцы" not in same
    assert "Повторы: 4 × 8" in changed
    assert "Вес: 60 кг" in changed
    assert "Усилие: 7\nФакт: 4×6 · 70 кг" in changed
    assert "\n\n" not in changed
    assert "<i>" not in changed


def test_sparse_exercise_keeps_name_and_prescription() -> None:
    text = format_planned_exercise_message(
        _slot(
            position=2,
            custom_request="Планка",
            muscle_group="кор",
            sets=3,
            reps=None,
            duration_seconds=40,
            weight_kg=None,
            rest_seconds=45,
            rpe=6,
        ),
        name="Планка",
        primary_muscles=["кор"],
    )
    assert text.split("\n", 1)[0] == "<b>Планка</b>"
    assert "💪 <b>Мышцы</b>\nкор" in text
    assert "📋 <b>План</b>\nВремя: 3 × 40 с\nОтдых: 45 с\nУсилие: 6" in text
    assert "Повторы" not in text
    assert "Вес" not in text
    assert "кг" not in text
    assert "\n\n" not in text
    assert "Техника" not in text
    assert "Видео" not in text
    assert "<blockquote>" not in text
    assert "<i>" not in text
    assert "<a " not in text


def test_technique_is_split_on_sentences_and_left_whole_without_them() -> None:
    grouped = format_planned_exercise_message(
        _slot(position=1, exercise_id=uuid4()),
        name="Присед",
        technique="Встань прямо. Смотри вперёд. Выдох на усилии.",
    )
    assert "✍️ <b>Техника</b>\nВстань прямо. Смотри вперёд.\nВыдох на усилии." in grouped
    assert "<blockquote>" not in grouped
    whole = format_planned_exercise_message(
        _slot(position=1, exercise_id=uuid4()),
        name="Планка",
        technique="держи корпус ровно и не прогибай поясницу",
    )
    assert whole.count("✍️") == 1
    assert "✍️ <b>Техника</b>\nдержи корпус ровно и не прогибай поясницу" in whole
    assert "<blockquote>" not in whole


async def test_pack_sends_in_order_and_sleeps_between_messages() -> None:
    calls: list[tuple[object, ...]] = []
    exercise_id = uuid4()
    day = WorkoutDay(
        weekday=1,
        title="Грудь & спина",
        position=2,
        warmup="Суставы <плеч>",
        cooldown="",
        slots=[
            _slot(
                position=2,
                custom_request="Планка",
                muscle_group="кор",
                sets=3,
                reps=None,
                duration_seconds=40,
                rest_seconds=45,
                rpe=6,
            ),
            _slot(position=1, exercise_id=exercise_id, weight_kg=Decimal("60")),
        ],
    )

    class _Message:
        async def answer(self, text: str, reply_markup=None, **kwargs: object) -> None:
            calls.append(
                ("send", text, reply_markup, kwargs.get("link_preview_options"), kwargs.get("parse_mode")),
            )

    async def _sleep(seconds: float) -> None:
        calls.append(("sleep", seconds))

    await present_planned_training_day(
        message=_Message(),
        day=day,
        day_position=2,
        names={exercise_id: "Жим лёжа"},
        guides={
            exercise_id: GetExerciseGuideResult(
                found=True,
                exercise_id=exercise_id,
                name="Жим лёжа",
                technique="Лягте на скамью.",
                primary_muscles=["грудь"],
                videos=[ExerciseGuideVideoItem(platform="rutube", url="https://rutube.ru/video/demo/", title="Демо")],
            ),
        },
        sleep=_sleep,
    )

    kinds = [item[0] for item in calls]
    assert kinds == ["send", "sleep", "send", "sleep", "send", "sleep", "send"]
    assert all(item[1] == EXERCISE_PACK_PAUSE_SECONDS for item in calls if item[0] == "sleep")
    texts = [item[1] for item in calls if item[0] == "send"]
    assert "Грудь &amp; спина" in texts[0]
    assert "Суставы &lt;плеч&gt;" in texts[0]
    assert "<b>Жим лёжа</b>" in texts[1]
    assert "Лягте на скамью." in texts[1]
    assert '▶️ <b>Видео</b>\nRutube: <a href="https://rutube.ru/video/demo/">Демо</a>' in texts[1]
    assert "<b>Планка</b>" in texts[2]
    assert texts[3] == "К программе или в меню."
    markups = [item[2] for item in calls if item[0] == "send"]
    assert markups[0] is None and markups[1] is None and markups[2] is None
    callbacks = [button.callback_data for row in markups[3].inline_keyboard for button in row]
    assert callbacks == ["prog", "home"]
    sends = [item for item in calls if item[0] == "send"]
    assert all(item[3] is not None and item[3].is_disabled for item in sends)
    assert all(item[4] == "HTML" for item in sends)


async def test_prog_view_day_pack_and_old_slot_callbacks() -> None:
    exercise_id = uuid4()
    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=3,
                title="Ноги",
                position=1,
                slots=[
                    _slot(position=1, exercise_id=exercise_id, weight_kg=Decimal("40")),
                ],
            ),
        ],
    )
    calls: list[tuple[object, ...]] = []

    class _Message:
        def __init__(self) -> None:
            self.answers: list[str] = []
            self.parse_modes: list[object] = []

        async def answer(self, text: str, reply_markup=None, **kwargs: object) -> None:
            self.answers.append(text)
            self.parse_modes.append(kwargs.get("parse_mode"))
            calls.append(("send", text, reply_markup))

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

    class _Mediator:
        async def send(self, request: object):
            if isinstance(request, GetActiveProgramQuery):
                return GetActiveProgramQueryResult(program_type=ProgramType.FULL_BODY, document=document)
            if isinstance(request, GetExerciseNamesQuery):
                return GetExerciseNamesResult(
                    names={str(exercise_id): "Присед"},
                    primary_muscles={str(exercise_id): ["квадрицепс"]},
                )
            if isinstance(request, GetExerciseGuideQuery):
                return GetExerciseGuideResult(
                    found=True,
                    name="Присед",
                    technique="Стопы на ширине плеч.",
                    primary_muscles=["квадрицепс"],
                    secondary_muscles=["ягодицы"],
                )
            raise AssertionError(type(request))

    router = create_program_router(jinja_env=create_jinja_env(), mediator=_Mediator())
    view = _handler(router, "handle_prog_view_day")
    message = _Message()
    callback = _Callback("prog_view_day:1", message)

    async def _sleep(seconds: float) -> None:
        calls.append(("sleep", seconds))

    with patch("fitness_bot.presentation.planned_day_pack.asyncio.sleep", _sleep):
        await view(callback)

    assert callback.answered == 1
    assert [item[0] for item in calls] == ["send", "sleep", "send", "sleep", "send"]
    assert calls[1] == ("sleep", EXERCISE_PACK_PAUSE_SECONDS)
    assert message.answers[1].split("\n", 1)[0] == "<b>Присед</b>"
    assert "💪 <b>Мышцы</b>\nквадрицепс, ягодицы" in message.answers[1]
    assert "📋 <b>План</b>\nПовторы: 4 × 8\nВес: 40 кг\nОтдых: 90 с\nУсилие: 7" in message.answers[1]
    assert "✍️ <b>Техника</b>\nСтопы на ширине плеч." in message.answers[1]
    assert "<blockquote>" not in message.answers[1]
    assert "<i>" not in message.answers[1]
    assert "<code>" not in message.answers[1]
    assert "<pre>" not in message.answers[1]
    assert message.parse_modes == ["HTML", "HTML", "HTML"]
    labels = [button.callback_data for row in calls[-1][2].inline_keyboard for button in row]
    assert "prog_view_slot" not in " ".join(labels)
    assert labels == ["prog", "home"]

    empty = _MediatorEmpty()
    router_old = create_program_router(jinja_env=create_jinja_env(), mediator=empty)
    for name, data in (
        ("handle_prog_view_slot", "prog_view_slot:1:1"),
        ("handle_prog_view_how", "prog_view_how:1:1"),
    ):
        handler = _handler(router_old, name)
        old_message = _Message()
        old_callback = _Callback(data, old_message)
        await handler(old_callback)
        assert old_callback.answered == 1
        assert old_message.answers == ["Активной программы нет."]


def _handler(router, name: str):
    return next(item.callback for item in router.callback_query.handlers if item.callback.__name__ == name)


class _MediatorEmpty:
    async def send(self, request: object):
        if isinstance(request, GetActiveProgramQuery):
            return GetActiveProgramQueryResult()
        raise AssertionError(type(request))
