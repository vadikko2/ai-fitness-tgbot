from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from fitness_bot.domain.enums import ProgramType, SessionStatus
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay, WorkoutDocument
from fitness_bot.presentation.keyboards import (
    SIMILAR_EXERCISE_LABEL,
    session_exercise_actions_keyboard,
    similar_exercises_keyboard,
    slot_actions_keyboard,
)
from fitness_bot.presentation.routers.session import create_session_router, show_similar_exercises
from fitness_bot.presentation.templates_env import create_jinja_env
from fitness_bot.service.models.commands.session import (
    SwapSessionSlotExerciseCommand,
    SwapSessionSlotExerciseCommandResult,
)
from fitness_bot.service.models.queries.match_exercises import (
    GetExerciseGuideQuery,
    GetExerciseGuideResult,
    GetExerciseNamesQuery,
    GetExerciseNamesResult,
)
from fitness_bot.service.models.queries.session import (
    GetSimilarExercisesQuery,
    GetSimilarExercisesQueryResult,
    GetTodayWorkoutQuery,
    GetTodayWorkoutQueryResult,
    SimilarExerciseItem,
)


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class _Message:
    def __init__(self) -> None:
        self.answers: list[tuple[str, object]] = []
        self.edits: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None, **_: object) -> None:
        self.answers.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None, **_: object) -> None:
        self.edits.append((text, reply_markup))


class _Mediator:
    def __init__(self, result: GetSimilarExercisesQueryResult) -> None:
        self.result = result
        self.requests: list[object] = []

    async def send(self, request):
        self.requests.append(request)
        assert isinstance(request, GetSimilarExercisesQuery)
        return self.result


def test_slot_screen_offers_similar_only_before_logging() -> None:
    open_slot = slot_actions_keyboard(position=3, has_catalog_guide=True, can_swap=True)
    assert "slot_alt:3" in _callbacks(open_slot)
    assert any(button.text == SIMILAR_EXERCISE_LABEL for row in open_slot.inline_keyboard for button in row)
    logged = slot_actions_keyboard(position=3, has_actual=True, has_catalog_guide=True)
    assert "slot_alt:3" not in _callbacks(logged)


def test_after_swap_offers_program_replace_and_revert() -> None:
    old_id = str(uuid4())
    callbacks = _callbacks(
        slot_actions_keyboard(
            position=12,
            can_swap=True,
            swapped_from=(old_id, "Жим штанги лёжа"),
            offer_program_swap=True,
        ),
    )
    assert "slot_swap_prog:12" in callbacks
    assert f"slot_swap:12:{old_id}" in callbacks
    assert all(len(data.encode()) <= 64 for data in callbacks)


def test_similar_keyboard_swaps_pages_and_goes_back() -> None:
    first, second = str(uuid4()), str(uuid4())
    markup = similar_exercises_keyboard(
        position=12,
        items=[(first, "Жим гантелей"), (second, "Отжимания")],
        next_offset=3,
    )
    callbacks = _callbacks(markup)
    assert callbacks == [f"slot_swap:12:{first}", f"slot_swap:12:{second}", "slot_alt:12:3", "slot_card:12"]
    assert [button.text for row in markup.inline_keyboard for button in row] == [
        "Жим гантелей",
        "Отжимания",
        "Ещё",
        "⬅️ Назад",
    ]
    assert all(len(data.encode()) <= 64 for data in callbacks)
    assert _callbacks(similar_exercises_keyboard(position=12, items=[])) == ["slot_card:12"]


async def test_similar_screen_lists_alternatives_and_wraps_paging() -> None:
    result = GetSimilarExercisesQueryResult(
        slot_position=1,
        exercise_name="Жим <лёжа>",
        primary_muscles=["грудь"],
        secondary_muscles=["трицепс"],
        items=[
            SimilarExerciseItem(
                exercise_id=uuid4(),
                name="Жим гантелей лёжа",
                primary_muscles=["грудь"],
                secondary_muscles=["плечи", "трицепс"],
            ),
            SimilarExerciseItem(exercise_id=uuid4(), name="Жим одной гантели лёжа", primary_muscles=["грудь"]),
        ],
        offset=3,
        has_more=False,
    )
    message = _Message()
    mediator = _Mediator(result)
    alert = await show_similar_exercises(
        jinja_env=create_jinja_env(),
        mediator=mediator,  # type: ignore[arg-type]
        message=message,
        telegram_user_id=1,
        position=1,
        offset=3,
    )
    assert alert is None
    assert message.answers == []
    text, markup = message.edits[0]
    assert text == "Вместо «Жим &lt;лёжа&gt;»"
    assert "Можно сделать" not in text
    assert "slot_alt:1:0" in _callbacks(markup)
    assert "slot_card:1" in _callbacks(markup)
    query = mediator.requests[0]
    assert isinstance(query, GetSimilarExercisesQuery)
    assert query.limit == 3


async def test_similar_screen_explains_logged_block() -> None:
    message = _Message()
    alert = await show_similar_exercises(
        jinja_env=create_jinja_env(),
        mediator=_Mediator(GetSimilarExercisesQueryResult(slot_position=2, blocked_reason="logged")),  # type: ignore[arg-type]
        message=message,
        telegram_user_id=1,
        position=2,
    )
    assert alert is not None
    assert "уже записан факт" in alert
    assert message.answers == []
    assert message.edits == []


def _slot(**kwargs: object) -> ExerciseSlot:
    payload: dict[str, object] = {"sets": 4, "reps": 8, "rest_seconds": 90, "rpe": 7, "weight_kg": Decimal("60")}
    payload.update(kwargs)
    return ExerciseSlot(**payload)  # type: ignore[arg-type]


def _handler(router, name: str):
    return next(item.callback for item in router.callback_query.handlers if item.callback.__name__ == name)


class _Card:
    def __init__(self, *, position: int) -> None:
        self.answers: list[tuple[str, object]] = []
        self.edits: list[tuple[str, object]] = []
        self.reply_markup = session_exercise_actions_keyboard(position=position)
        self.html_text = "<b>Жим штанги</b>\n<blockquote>Лягте на скамью.</blockquote>"
        self.text = self.html_text

    async def answer(self, text: str, reply_markup=None, **_: object) -> None:
        self.answers.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None, **_: object) -> None:
        self.edits.append((text, reply_markup))
        self.html_text = text
        self.text = text
        self.reply_markup = reply_markup


class _Tap:
    def __init__(self, data: str, message: _Card) -> None:
        self.data = data
        self.from_user = type("User", (), {"id": 7})()
        self.message = message
        self.replies: list[tuple[object, dict[str, object]]] = []

    async def answer(self, text: object = None, **kwargs: object) -> None:
        self.replies.append((text, kwargs))


class _Flow:
    def __init__(self, *, blocked: str | None = None, fail_swap: bool = False) -> None:
        self._blocked = blocked
        self._fail_swap = fail_swap
        self.current_id = uuid4()
        self.alt_id = uuid4()
        self.more_ids = [uuid4(), uuid4()]
        self.slot = _slot(position=2, exercise_id=self.current_id, weight_kg=Decimal("60"))
        self.document = WorkoutDocument(
            program_type=ProgramType.FULL_BODY,
            days=[WorkoutDay(weekday=1, title="Грудь", position=1, slots=[self.slot])],
        )
        self.requests: list[object] = []

    async def send(self, request: object):
        self.requests.append(request)
        if isinstance(request, GetSimilarExercisesQuery):
            if self._blocked == "logged":
                return GetSimilarExercisesQueryResult(slot_position=request.slot_position, blocked_reason="logged")
            if request.offset == 0:
                return GetSimilarExercisesQueryResult(
                    slot_position=2,
                    exercise_name="Жим штанги",
                    items=[
                        SimilarExerciseItem(exercise_id=self.alt_id, name="Жим гантелей"),
                        SimilarExerciseItem(exercise_id=self.more_ids[0], name="Отжимания"),
                        SimilarExerciseItem(exercise_id=self.more_ids[1], name="Сведения"),
                    ],
                    offset=0,
                    has_more=True,
                )
            return GetSimilarExercisesQueryResult(
                slot_position=2,
                exercise_name="Жим штанги",
                items=[
                    SimilarExerciseItem(exercise_id=self.more_ids[0], name="Жим в тренажёре"),
                    SimilarExerciseItem(exercise_id=self.more_ids[1], name="Отжимания на брусьях"),
                ],
                offset=request.offset,
                has_more=False,
            )
        if isinstance(request, SwapSessionSlotExerciseCommand):
            if self._fail_swap:
                raise DomainError("exercise with logged sets cannot be swapped")
            swapped = self.slot.model_copy(
                update={"exercise_id": request.exercise_id, "weight_kg": Decimal("22"), "technique_note": ""},
            )
            return SwapSessionSlotExerciseCommandResult(
                session_id=uuid4(),
                document=self.document,
                slot=swapped,
                previous_exercise_id=self.current_id,
                weight_source="history",
                matches_program=False,
                can_replace_in_program=True,
            )
        if isinstance(request, GetTodayWorkoutQuery):
            return GetTodayWorkoutQueryResult(
                screen="session",
                document=self.document,
                session_status=SessionStatus.IN_PROGRESS,
            )
        if isinstance(request, GetExerciseNamesQuery):
            return GetExerciseNamesResult(
                names={
                    str(self.current_id): "Жим штанги",
                    str(self.alt_id): "Жим гантелей",
                },
            )
        if isinstance(request, GetExerciseGuideQuery):
            if request.exercise_id == self.alt_id:
                name, technique = "Жим гантелей", "Держи гантели."
            else:
                name, technique = "Жим штанги", "Лягте на скамью."
            return GetExerciseGuideResult(
                found=True,
                exercise_id=request.exercise_id,
                name=name,
                technique=technique,
                primary_muscles=["грудь"],
            )
        raise AssertionError(type(request))


def _router(flow: _Flow):
    return create_session_router(jinja_env=create_jinja_env(), mediator=flow)  # type: ignore[arg-type]


def _texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


async def test_similar_picker_edits_the_same_card() -> None:
    flow = _Flow()
    card = _Card(position=2)
    await _handler(_router(flow), "handle_slot_alt")(_Tap("slot_alt:2", card))

    assert card.answers == []
    assert len(card.edits) == 1
    text, markup = card.edits[0]
    assert text == "Вместо «Жим штанги»"
    assert "Лягте" not in text
    assert _texts(markup) == ["Жим гантелей", "Отжимания", "Сведения", "Ещё", "⬅️ Назад"]
    assert _callbacks(markup)[0] == f"slot_swap:2:{flow.alt_id}"
    assert _callbacks(markup)[-2:] == ["slot_alt:2:3", "slot_card:2"]


async def test_picking_alternative_swaps_into_the_same_card() -> None:
    flow = _Flow()
    card = _Card(position=2)
    router = _router(flow)
    await _handler(router, "handle_slot_alt")(_Tap("slot_alt:2", card))
    await _handler(router, "handle_slot_swap")(_Tap(f"slot_swap:2:{flow.alt_id}", card))

    assert card.answers == []
    text, markup = card.edits[-1]
    assert text.count("Держи гантели.") == 1
    assert "<b>Жим гантелей</b>" in text
    assert "<i>Подходы:</i> 4" in text
    assert "<i>Повторы:</i> 8" in text
    assert "<i>Вес:</i> 22 кг" in text
    assert "Вернуть" not in text
    assert "программе" not in text
    assert _texts(markup) == ["✅ Выполнить", "✏️ Вес и повторы", "🔄 Похожее упражнение"]
    assert _callbacks(markup) == ["slot_plan:2", "slot_fact:2", "slot_alt:2"]
    swaps = [item for item in flow.requests if isinstance(item, SwapSessionSlotExerciseCommand)]
    assert len(swaps) == 1
    assert swaps[0].slot_position == 2
    assert swaps[0].exercise_id == flow.alt_id


async def test_back_restores_the_original_card_without_swapping() -> None:
    flow = _Flow()
    card = _Card(position=2)
    router = _router(flow)
    await _handler(router, "handle_slot_alt")(_Tap("slot_alt:2", card))
    await _handler(router, "handle_slot_card")(_Tap("slot_card:2", card))

    assert card.answers == []
    text, markup = card.edits[-1]
    assert "<b>Жим штанги</b>" in text
    assert text.count("Лягте на скамью.") == 1
    assert _texts(markup) == ["✅ Выполнить", "✏️ Вес и повторы", "🔄 Похожее упражнение"]
    assert not any(isinstance(item, SwapSessionSlotExerciseCommand) for item in flow.requests)


async def test_more_button_edits_the_next_names() -> None:
    flow = _Flow()
    card = _Card(position=2)
    router = _router(flow)
    await _handler(router, "handle_slot_alt")(_Tap("slot_alt:2", card))
    await _handler(router, "handle_slot_alt")(_Tap("slot_alt:2:3", card))

    assert card.answers == []
    text, markup = card.edits[-1]
    assert text == "Вместо «Жим штанги»"
    assert _texts(markup) == ["Жим в тренажёре", "Отжимания на брусьях", "Ещё", "⬅️ Назад"]
    assert _callbacks(markup)[-2:] == ["slot_alt:2:0", "slot_card:2"]


async def test_logged_slot_alerts_and_keeps_the_card_keyboard() -> None:
    flow = _Flow(blocked="logged")
    card = _Card(position=2)
    tap = _Tap("slot_alt:2", card)
    await _handler(_router(flow), "handle_slot_alt")(tap)

    assert card.answers == []
    assert card.edits == []
    assert _callbacks(card.reply_markup) == ["slot_plan:2", "slot_fact:2", "slot_alt:2"]
    assert tap.replies == [("По этому упражнению уже записан факт — заменить его нельзя.", {"show_alert": True})]


async def test_failed_swap_alerts_and_restores_the_card_keyboard() -> None:
    flow = _Flow(fail_swap=True)
    card = _Card(position=2)
    router = _router(flow)
    await _handler(router, "handle_slot_alt")(_Tap("slot_alt:2", card))
    tap = _Tap(f"slot_swap:2:{flow.alt_id}", card)
    await _handler(router, "handle_slot_swap")(tap)

    assert card.answers == []
    assert _callbacks(card.reply_markup) == ["slot_plan:2", "slot_fact:2", "slot_alt:2"]
    assert tap.replies[-1][1].get("show_alert") is True
    assert "заменить" in str(tap.replies[-1][0])


async def test_old_similar_callbacks_do_not_crash() -> None:
    flow = _Flow()
    card = _Card(position=2)
    router = _router(flow)
    for data, name in (
        ("slot_swap:2", "handle_slot_swap"),
        ("slot_swap:2:not-a-uuid", "handle_slot_swap"),
        ("slot_alt:", "handle_slot_alt"),
        ("slot_alt:nope", "handle_slot_alt"),
        ("slot_card:", "handle_slot_card"),
        ("slot:abc", "handle_slot"),
    ):
        await _handler(router, name)(_Tap(data, card))

    assert card.answers == []
    assert not any(isinstance(item, SwapSessionSlotExerciseCommand) for item in flow.requests)
