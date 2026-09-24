from __future__ import annotations

from uuid import UUID, uuid4

from fitness_bot.domain.enums import ProgramType
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay, WorkoutDocument
from fitness_bot.service.handlers.commands.agent_json import parse_workout_document


def test_parse_workout_document_fills_sparse_slot_defaults() -> None:
    exercise_id = UUID("54648257-b93d-4363-9792-123cabd7a4d3")
    document = parse_workout_document(
        {
            "days": [
                {
                    "weekday": 1,
                    "type": "full_body",
                    "slots": [{"exercise_id": str(exercise_id)}],
                },
            ],
        },
        default_program_type=ProgramType.FULL_BODY,
    )
    assert document.program_type == ProgramType.FULL_BODY
    assert len(document.days) == 1
    day = document.days[0]
    assert day.title == "день 1"
    assert day.position == 1
    assert day.intensity.value == "medium"
    slot = day.slots[0]
    assert slot.position == 1
    assert slot.exercise_id == exercise_id
    assert slot.sets == 3
    assert slot.reps == 10
    assert slot.rest_seconds == 90
    assert slot.rpe == 7


def test_parse_workout_document_reads_day_intensity() -> None:
    exercise_id = UUID("54648257-b93d-4363-9792-123cabd7a4d3")
    document = parse_workout_document(
        {
            "program_type": "split",
            "days": [
                {
                    "weekday": 2,
                    "title": "Тяжелая",
                    "position": 1,
                    "intensity": "heavy",
                    "slots": [{"exercise_id": str(exercise_id), "sets": 4, "reps": 5, "rest_seconds": 120, "rpe": 8}],
                },
            ],
        },
    )
    assert document.days[0].intensity.value == "heavy"


def test_parse_workout_document_salvages_non_uuid_exercise_id() -> None:
    document = parse_workout_document(
        {
            "program_type": "push_pull",
            "days": [
                {
                    "weekday": 1,
                    "title": "Жимы",
                    "position": 1,
                    "slots": [
                        {
                            "exercise_id": "Жим лёжа",
                            "sets": 3,
                            "reps": 8,
                            "rest_seconds": 90,
                            "rpe": 7,
                        },
                    ],
                },
            ],
        },
    )
    slot = document.days[0].slots[0]
    assert slot.exercise_id is None
    assert slot.custom_request == "Жим лёжа"
    assert slot.muscle_group == "общее"


def test_parse_workout_document_ignores_truncated_uuid() -> None:
    document = parse_workout_document(
        {
            "program_type": "push_pull",
            "days": [
                {
                    "weekday": 1,
                    "title": "Тяги",
                    "position": 1,
                    "slots": [{"exercise_id": "54648257-b93d-4363-9792", "reps": 10}],
                },
            ],
        },
    )
    slot = document.days[0].slots[0]
    assert slot.exercise_id is None
    assert slot.custom_request == "54648257-b93d-4363-9792"
    assert slot.muscle_group == "общее"


def test_with_unknown_ids_unresolved() -> None:
    known = uuid4()
    unknown = uuid4()
    document = WorkoutDocument(
        program_type=ProgramType.PUSH_PULL,
        days=[
            WorkoutDay(
                weekday=1,
                title="Жимы",
                position=1,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=known,
                        sets=3,
                        reps=8,
                        rest_seconds=90,
                        rpe=7,
                    ),
                    ExerciseSlot(
                        position=2,
                        exercise_id=unknown,
                        sets=3,
                        reps=10,
                        rest_seconds=60,
                        rpe=7,
                    ),
                ],
            ),
        ],
    )
    cleaned = document.with_unknown_ids_unresolved({known})
    assert cleaned.days[0].slots[0].exercise_id == known
    assert cleaned.days[0].slots[1].exercise_id is None
    assert cleaned.days[0].slots[1].custom_request == "уточнить упражнение"
    assert cleaned.days[0].slots[1].muscle_group == "общее"
