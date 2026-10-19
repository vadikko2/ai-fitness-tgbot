"""Weight and reps stay on the live exercise card. No extra chat bubble."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from fitness_bot.domain.enums import ExpectedInput, ProgramType, SessionStatus
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay, WorkoutDocument
from fitness_bot.presentation.routers.session import (
    create_session_router,
    handle_slot_load_utterance,
    handle_slot_weight_utterance,
)
from fitness_bot.presentation.templates_env import create_jinja_env
from fitness_bot.service.models.commands.session import RecordSlotActualCommand, RecordSlotActualCommandResult
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.match_exercises import (
    GetExerciseGuideQuery,
    GetExerciseGuideResult,
    GetExerciseNamesQuery,
    GetExerciseNamesResult,
)
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery, GetTodayWorkoutQueryResult
from fitness_bot.service.models.queries.users import GetWorkflowQuery, GetWorkflowQueryResult

_NAME = "Жим <наклонной>"
_QUOTED = "Жим &lt;наклонной&gt;"


def _slot(**kwargs: object) -> ExerciseSlot:
    payload: dict[str, object] = {
        "position": 2,
        "exercise_id": uuid4(),
        "sets": 3,
        "reps": 10,
        "weight_kg": Decimal("16"),
        "rest_seconds": 60,
        "rpe": 7,
    }
    payload.update(kwargs)
    return ExerciseSlot(**payload)  # type: ignore[arg-type]


class _Card:
    def __init__(self) -> None:
        self.message_id = 15
        self.answers: list[str] = []
        self.edits: list[tuple[str, object]] = []
        self.parse_modes: list[object] = []
        self.reply_markup = None
        self.html_text = ""
        self.text = ""

    async def answer(self, text: str, reply_markup=None, **_: object) -> None:
        self.answers.append(text)

    async def edit_text(self, text: str, reply_markup=None, **kwargs: object) -> None:
        self.edits.append((text, reply_markup))
        self.parse_modes.append(kwargs.get("parse_mode"))
        self.html_text = text
        self.text = text
        self.reply_markup = reply_markup


class _Bot:
    def __init__(self) -> None:
        self.edits: list[tuple[int, int, str, object, object]] = []

    async def edit_message_text(
        self,
        text: str,
        *,
        chat_id: int,
        message_id: int,
        reply_markup=None,
        **kwargs: object,
    ) -> None:
        self.edits.append((chat_id, message_id, text, reply_markup, kwargs.get("parse_mode")))


class _Typed:
    def __init__(self, bot: _Bot) -> None:
        self.bot = bot
        self.chat = type("Chat", (), {"id": 9})()
        self.message_id = 99
        self.from_user = type("User", (), {"id": 7})()
        self.answers: list[str] = []

    async def answer(self, text: str, reply_markup=None, **_: object) -> None:
        self.answers.append(text)


class _Tap:
    def __init__(self, data: str, message: _Card) -> None:
        self.data = data
        self.from_user = type("User", (), {"id": 7})()
        self.message = message

    async def answer(self, *args: object, **kwargs: object) -> None:
        return None


class _Flow:
    def __init__(self, slot: ExerciseSlot) -> None:
        self.slot = slot
        self.exercise_id = slot.exercise_id or uuid4()
        if slot.exercise_id is None:
            self.slot = slot.model_copy(update={"exercise_id": self.exercise_id})
        self.document = WorkoutDocument(
            program_type=ProgramType.FULL_BODY,
            days=[WorkoutDay(weekday=1, title="Грудь", position=1, slots=[self.slot])],
        )
        self.expected_input = ExpectedInput.NONE
        self.expected_field: str | None = None
        self.focus_slot: int | None = None
        self.recorded: list[RecordSlotActualCommand] = []

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
            return GetExerciseNamesResult(names={str(self.exercise_id): _NAME})
        if isinstance(request, GetExerciseGuideQuery):
            return GetExerciseGuideResult(found=False)
        if isinstance(request, RecordSlotActualCommand):
            updated = self.slot.with_actual(
                SlotActual(
                    sets=request.sets,
                    reps=request.reps,
                    duration_seconds=request.duration_seconds,
                    weight_kg=request.weight_kg,
                ),
            )
            self.recorded.append(request)
            return RecordSlotActualCommandResult(session_id=uuid4(), slot=updated, document=self.document)
        raise AssertionError(type(request))


def _handler(router, name: str):
    return next(item.callback for item in router.callback_query.handlers if item.callback.__name__ == name)


def _router(flow: _Flow):
    return create_session_router(jinja_env=create_jinja_env(), mediator=flow)  # type: ignore[arg-type]


def _texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _legacy(markup) -> bool:
    labels = _texts(markup)
    callbacks = _callbacks(markup)
    return "Как делать" in " ".join(labels) or "Назад к тренировке" in " ".join(labels) or "slot:2" in callbacks


async def test_weight_step_edits_the_same_card() -> None:
    flow = _Flow(_slot())
    card = _Card()
    await _handler(_router(flow), "handle_slot_fact")(_Tap("slot_fact:2", card))

    assert card.answers == []
    assert len(card.edits) == 1
    assert card.parse_modes == ["HTML"]
    text, markup = card.edits[0]
    assert text == f"Вес для «{_QUOTED}». В плане: 16 кг. Напиши число или выбери."
    assert _texts(markup) == ["Как в плане · 16 кг", "Без веса", "⬅️ Назад"]
    assert _callbacks(markup) == ["slot_w_plan:2", "slot_w_none:2", "slot_card:2"]
    assert not _legacy(markup)
    assert flow.expected_input == ExpectedInput.SLOT_WEIGHT
    assert flow.expected_field == "@15"
    assert flow.focus_slot == 2


async def test_weight_back_restores_the_live_card() -> None:
    flow = _Flow(_slot())
    card = _Card()
    router = _router(flow)
    await _handler(router, "handle_slot_fact")(_Tap("slot_fact:2", card))
    await _handler(router, "handle_slot_card")(_Tap("slot_card:2", card))

    assert card.answers == []
    assert card.parse_modes == ["HTML", "HTML"]
    text, markup = card.edits[-1]
    assert text.startswith(f"<b>{_QUOTED}</b>")
    assert "📋 <b>План</b>\nПовторы: 3 × 10\nВес: 16 кг\nОтдых: 60 с\nУсилие: 7" in text
    assert "\n\n" not in text
    assert "Факт:" not in text
    assert _texts(markup) == ["▶️ Выполнить", "✏️ Вес и повторы", "🔄 Похожее упражнение"]
    assert _callbacks(markup) == ["slot_plan:2", "slot_fact:2", "slot_alt:2"]
    assert not _legacy(markup)
    assert flow.expected_input == ExpectedInput.NONE
    assert flow.recorded == []


async def test_plan_weight_then_back_returns_to_the_weight_step() -> None:
    flow = _Flow(_slot())
    card = _Card()
    router = _router(flow)
    await _handler(router, "handle_slot_fact")(_Tap("slot_fact:2", card))
    await _handler(router, "handle_slot_w_plan")(_Tap("slot_w_plan:2", card))

    assert card.answers == []
    text, markup = card.edits[-1]
    assert text == f"Повторы для «{_QUOTED}». В плане: 10. Напиши число или выбери."
    assert _texts(markup) == ["Как в плане · 10", "⬅️ Назад"]
    assert _callbacks(markup) == ["slot_r_plan:2", "slot_fact:2"]
    assert flow.expected_input == ExpectedInput.SLOT_LOAD
    assert flow.expected_field == "16@15"

    await _handler(router, "handle_slot_fact")(_Tap("slot_fact:2", card))

    assert card.answers == []
    text, markup = card.edits[-1]
    assert text.startswith("Вес для ")
    assert _callbacks(markup)[-1] == "slot_card:2"
    assert flow.recorded == []


async def test_plan_choices_return_the_done_card_on_the_same_message() -> None:
    flow = _Flow(_slot())
    card = _Card()
    router = _router(flow)
    await _handler(router, "handle_slot_fact")(_Tap("slot_fact:2", card))
    await _handler(router, "handle_slot_w_none")(_Tap("slot_w_none:2", card))
    await _handler(router, "handle_slot_r_plan")(_Tap("slot_r_plan:2", card))

    assert card.answers == []
    assert card.parse_modes[-1] == "HTML"
    text, markup = card.edits[-1]
    assert "Вес для" not in text
    assert "Повторы для" not in text
    assert "📋 <b>План</b>\nПовторы: 3 × 10\nВес: 16 кг\nОтдых: 60 с\nУсилие: 7" in text
    assert "Факт: 3×10" in text
    assert "кг" not in text.split("Факт:", 1)[1]
    assert "\n\n" not in text
    assert _texts(markup)[0] == "✅ Выполнено"
    assert _callbacks(markup) == ["slot_undo:2", "slot_fact:2", "slot_alt:2"]
    assert not _legacy(markup)
    assert len(flow.recorded) == 1
    assert flow.recorded[0].weight_kg is None
    assert flow.recorded[0].reps == 10


async def test_typed_numbers_edit_the_stored_card_and_fill_the_fact() -> None:
    flow = _Flow(_slot())
    card = _Card()
    router = _router(flow)
    await _handler(router, "handle_slot_fact")(_Tap("slot_fact:2", card))
    bot = _Bot()
    typed = _Typed(bot)

    await handle_slot_weight_utterance(mediator=flow, message=typed, text="20,5", focus_slot=2)  # type: ignore[arg-type]

    assert typed.answers == []
    assert card.answers == []
    assert len(bot.edits) == 1
    chat_id, message_id, text, markup, parse_mode = bot.edits[0]
    assert (chat_id, message_id, parse_mode) == (9, 15, "HTML")
    assert text == f"Повторы для «{_QUOTED}». В плане: 10. Напиши число или выбери."
    assert _texts(markup) == ["Как в плане · 10", "⬅️ Назад"]

    await handle_slot_load_utterance(
        mediator=flow,  # type: ignore[arg-type]
        message=typed,  # type: ignore[arg-type]
        text="8",
        focus_slot=2,
        draft_weight=flow.expected_field,
    )

    assert typed.answers == []
    assert len(bot.edits) == 2
    _, message_id, text, markup, parse_mode = bot.edits[1]
    assert message_id == 15
    assert parse_mode == "HTML"
    assert "Повторы для" not in text
    assert "📋 <b>План</b>\nПовторы: 3 × 10\nВес: 16 кг" in text
    assert "Факт: 3×8 · 20.5 кг" in text
    assert "\n\n" not in text
    assert _texts(markup)[0] == "✅ Выполнено"
    assert flow.recorded[0].weight_kg == Decimal("20.5")
    assert flow.recorded[0].reps == 8


async def test_timed_slot_asks_for_time_on_the_same_card() -> None:
    flow = _Flow(_slot(reps=None, duration_seconds=45, weight_kg=Decimal("16")))
    card = _Card()
    router = _router(flow)
    await _handler(router, "handle_slot_fact")(_Tap("slot_fact:2", card))
    await _handler(router, "handle_slot_w_plan")(_Tap("slot_w_plan:2", card))

    assert card.answers == []
    text, markup = card.edits[-1]
    assert text == f"Время для «{_QUOTED}». В плане: 45 с. Напиши число или выбери."
    assert _texts(markup) == ["Как в плане · 45 с", "⬅️ Назад"]
    assert _callbacks(markup) == ["slot_r_plan:2", "slot_fact:2"]


async def test_missing_plan_weight_omits_the_plan_button() -> None:
    flow = _Flow(_slot(weight_kg=None))
    card = _Card()
    await _handler(_router(flow), "handle_slot_fact")(_Tap("slot_fact:2", card))

    text, markup = card.edits[-1]
    assert text == f"Вес для «{_QUOTED}». Напиши число или выбери."
    assert _texts(markup) == ["Без веса", "⬅️ Назад"]
    assert _callbacks(markup) == ["slot_w_none:2", "slot_card:2"]
    assert card.answers == []
