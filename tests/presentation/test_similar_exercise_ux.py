from __future__ import annotations

from uuid import uuid4

from fitness_bot.presentation.keyboards import (
    SIMILAR_EXERCISE_LABEL,
    similar_exercises_keyboard,
    slot_actions_keyboard,
)
from fitness_bot.presentation.routers.session import show_similar_exercises
from fitness_bot.presentation.templates_env import create_jinja_env
from fitness_bot.service.models.queries.session import (
    GetSimilarExercisesQuery,
    GetSimilarExercisesQueryResult,
    SimilarExerciseItem,
)


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class _Message:
    def __init__(self) -> None:
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None, **_: object) -> None:
        self.answers.append((text, reply_markup))


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
    callbacks = _callbacks(
        similar_exercises_keyboard(position=12, items=[(first, "Жим гантелей"), (second, "Отжимания")], next_offset=3),
    )
    assert callbacks == [f"slot_swap:12:{first}", f"slot_swap:12:{second}", "slot_alt:12:3", "slot:12"]
    assert all(len(data.encode()) <= 64 for data in callbacks)
    assert "slot_alt:12:3" not in _callbacks(similar_exercises_keyboard(position=12, items=[]))


async def test_similar_screen_lists_alternatives_and_wraps_paging() -> None:
    result = GetSimilarExercisesQueryResult(
        slot_position=1,
        exercise_name="Жим штанги лёжа",
        primary_muscles=["грудь"],
        secondary_muscles=["трицепс"],
        items=[SimilarExerciseItem(exercise_id=uuid4(), name="Жим гантелей лёжа", primary_muscles=["грудь"])],
        offset=3,
        has_more=False,
    )
    message = _Message()
    await show_similar_exercises(
        jinja_env=create_jinja_env(),
        mediator=_Mediator(result),  # type: ignore[arg-type]
        message=message,  # type: ignore[arg-type]
        telegram_user_id=1,
        position=1,
        offset=3,
    )
    text, markup = message.answers[0]
    assert "Вместо «Жим штанги лёжа»" in text
    assert "Жим гантелей лёжа" in text
    assert "только в сегодняшней тренировке" in text
    assert "slot_alt:1:0" in _callbacks(markup)


async def test_similar_screen_explains_logged_block() -> None:
    message = _Message()
    await show_similar_exercises(
        jinja_env=create_jinja_env(),
        mediator=_Mediator(GetSimilarExercisesQueryResult(slot_position=2, blocked_reason="logged")),  # type: ignore[arg-type]
        message=message,  # type: ignore[arg-type]
        telegram_user_id=1,
        position=2,
    )
    text, markup = message.answers[0]
    assert "уже записан факт" in text
    assert "slot:2" in _callbacks(markup)
