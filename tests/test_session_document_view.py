from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from fitness_bot.domain.enums import ProgramType, WorkoutIntensity
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay, WorkoutDocument
from fitness_bot.presentation.routers.program import _slot_view as program_slot_view
from fitness_bot.presentation.routers.session import _document_view
from fitness_bot.presentation.templates_env import create_jinja_env


def test_document_view_includes_weekday_label_and_exercise_name() -> None:
    exercise_id = uuid4()
    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="День 1",
                position=1,
                intensity=WorkoutIntensity.HEAVY,
                warmup="разминка суставов",
                cooldown="спокойная ходьба",
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=exercise_id,
                        sets=3,
                        reps=8,
                        rest_seconds=60,
                        rpe=7,
                    ),
                ],
            ),
        ],
    )
    view = _document_view(document, {exercise_id: "Жим лёжа"})
    day = view["days"][0]
    assert day["weekday_label"] == "Пн"
    assert day["intensity"] == "heavy"
    assert day["intensity_label"] == "тяжелая"
    assert day["warmup"] == "разминка суставов"
    assert day["cooldown"] == "спокойная ходьба"
    assert day["slots"][0]["exercise_name"] == "Жим лёжа"


def test_proposal_and_session_templates_render_with_session_document_view() -> None:
    exercise_id = uuid4()
    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=3,
                title="День 1",
                position=1,
                intensity=WorkoutIntensity.LIGHT,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=exercise_id,
                        sets=3,
                        reps=10,
                        rest_seconds=90,
                        rpe=6,
                    ),
                ],
            ),
        ],
    )
    view = _document_view(document, {exercise_id: "Присед"})
    env = create_jinja_env()
    proposal = env.get_template("proposal.j2").render(
        reply="ок",
        document=view,
        program_type_label="фуллбади",
        missing_weekdays=False,
    )
    assert "Ср" in proposal
    assert "Легкая тренировка" in proposal
    template = env.get_template("session_template.j2").render(
        document=view,
        weekday_label="Ср",
        planned_count=3,
        completed_count=1,
        week_finished=False,
    )
    assert "Присед" in template
    assert "легкая" in template
    assert str(exercise_id) not in template
    card = env.get_template("session_card.j2").render(document=view)
    assert "легкая" in card
    assert "Присед" in card
    assert "\n1. Присед" in card or card.count("\n") >= 3
    day = env.get_template("proposal_day.j2").render(day=view["days"][0], reply="")
    assert "Легкая тренировка" in day

    warm_view = view["days"][0] | {"warmup": "5 мин кардио", "cooldown": "растяжка"}
    warm_day = env.get_template("proposal_day.j2").render(day=warm_view, reply="готово")
    assert "Разминка" in warm_day
    assert "5 мин кардио" in warm_day
    assert "Заминка" in warm_day
    assert "готово" in warm_day


def test_session_card_marks_actual_with_green_check_emoji() -> None:
    exercise_id = uuid4()
    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="День 1",
                position=1,
                intensity=WorkoutIntensity.MEDIUM,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=exercise_id,
                        sets=4,
                        reps=8,
                        rest_seconds=90,
                        rpe=7,
                        actual=SlotActual(sets=4, reps=8),
                    ),
                    ExerciseSlot(
                        position=2,
                        exercise_id=exercise_id,
                        sets=3,
                        reps=10,
                        rest_seconds=60,
                        rpe=6,
                    ),
                ],
            ),
        ],
    )
    view = _document_view(document, {exercise_id: "Жим"})
    card = create_jinja_env().get_template("session_card.j2").render(document=view)
    assert "✅" in card
    assert "✓" not in card
    assert "<b>🏋️ Тренировка сегодня</b>" in card
    lines = [line for line in card.splitlines() if line.strip() and line.lstrip()[0].isdigit()]
    assert len(lines) == 2
    assert lines[0].endswith("✅")
    assert "✅" not in lines[1]
    assert "<b>Жим</b>" in lines[0]


def test_program_and_session_slot_templates_include_planned_weight() -> None:
    exercise_id = uuid4()
    slot = ExerciseSlot(
        position=1,
        exercise_id=exercise_id,
        sets=3,
        reps=12,
        weight_kg=Decimal("100"),
        rest_seconds=90,
        rpe=7,
    )
    env = create_jinja_env()
    program_text = env.get_template("program_slot.j2").render(
        slot=program_slot_view(slot, {exercise_id: "Жим ногами"}),
    )
    assert "100 кг" in program_text
    assert "3×12" in program_text

    document = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="День 1",
                position=1,
                intensity=WorkoutIntensity.MEDIUM,
                slots=[slot],
            ),
        ],
    )
    view = _document_view(document, {exercise_id: "Жим ногами"})
    day_text = env.get_template("proposal_day.j2").render(day=view["days"][0], reply="")
    assert "100 кг" in day_text
    card = env.get_template("session_card.j2").render(document=view)
    assert "100 кг" in card
