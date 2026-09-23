from __future__ import annotations

from uuid import UUID

from fitness_bot.domain.enums import ProgramType
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
