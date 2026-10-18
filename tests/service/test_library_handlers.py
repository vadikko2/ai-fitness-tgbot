from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from fitness_bot.domain.enums import ProgramStatus, ProgramType, TrainingStyle, WorkoutIntensity
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.program_catalog import program_type_label
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay, WorkoutDocument
from fitness_bot.domain.workout.program import Program, default_library_title
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.handlers.commands.catalog import (
    ApplyCatalogProgramCommandHandler,
    ClaimProgramByCodeCommandHandler,
    DeleteLibraryProgramCommandHandler,
    ProposeLibraryProgramEditCommandHandler,
    PublishProgramCommandHandler,
    RenameLibraryProgramCommandHandler,
    SaveProgramDraftCommandHandler,
)
from fitness_bot.service.handlers.commands.program import ApproveProposalCommandHandler
from fitness_bot.service.handlers.commands.users import EnsureUserCommandHandler
from fitness_bot.service.handlers.queries.coach import ListProgramCatalogQueryHandler
from fitness_bot.service.models.commands.catalog import (
    ApplyCatalogProgramCommand,
    ClaimProgramByCodeCommand,
    DeleteLibraryProgramCommand,
    ProposeLibraryProgramEditCommand,
    PublishProgramCommand,
    RenameLibraryProgramCommand,
    SaveProgramDraftCommand,
)
from fitness_bot.service.models.commands.program import ApproveProposalCommand
from fitness_bot.service.models.commands.users import EnsureUserCommand
from fitness_bot.service.models.queries.coach import ListProgramCatalogQuery
from fitness_bot.service.ports.exercise_catalog import InMemoryExerciseCatalog, record

EX_A = uuid4()
EX_B = uuid4()


class ScriptedLanguageModel:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def complete(self, *, system: str, user: str) -> str:
        _ = system, user
        return self._responses.pop(0)


def _catalog() -> InMemoryExerciseCatalog:
    return InMemoryExerciseCatalog(
        exercises=[
            record(exercise_id=EX_A, name="Жим лёжа", primary_muscles=["грудь"]),
            record(exercise_id=EX_B, name="Тяга штанги", primary_muscles=["спина"]),
        ],
    )


def _doc(exercise_id=EX_A, *, sets: int = 3) -> WorkoutDocument:
    return WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="A",
                position=1,
                intensity=WorkoutIntensity.MEDIUM,
                training_style=TrainingStyle.CLASSIC,
                slots=[
                    ExerciseSlot(position=1, exercise_id=exercise_id, sets=sets, reps=10, rest_seconds=90, rpe=7),
                ],
            ),
        ],
    )


def _edit_json(*, exercise_id=EX_B, sets: int = 5) -> str:
    return json.dumps(
        {"document": _doc(exercise_id, sets=sets).model_dump(mode="json"), "reply": "Заменил жим на тягу."},
        ensure_ascii=False,
    )


async def _user(uow: InMemoryUow, telegram_id: int) -> None:
    await EnsureUserCommandHandler(uow).handle(EnsureUserCommand(telegram_user_id=telegram_id, chat_id=telegram_id))


async def _save(uow: InMemoryUow, telegram_id: int = 7, *, title: str | None = None):
    return await SaveProgramDraftCommandHandler(uow).handle(
        SaveProgramDraftCommand(telegram_user_id=telegram_id, document=_doc(), title=title),
    )


async def _card(uow: InMemoryUow, program_id) -> Program:
    async with uow.transaction() as repos:
        card = await repos.programs.get_by_id(program_id)
    assert card is not None
    return card


def test_default_library_title_has_type_days_and_date() -> None:
    title = default_library_title(_doc(), now=datetime(2026, 10, 18, tzinfo=UTC))
    assert title == f"{program_type_label(ProgramType.FULL_BODY)} · 1 день · 18.10.2026"


def test_rename_validates_title() -> None:
    program = Program.draft_from_document(user_id=uuid4(), document=_doc(), title="x")
    program.rename("  Моя   сила  ")
    assert program.title == "Моя сила"
    with pytest.raises(DomainError):
        program.rename("   ")
    with pytest.raises(DomainError):
        program.rename("я" * 61)


async def test_save_without_title_uses_distinct_auto_names() -> None:
    uow = InMemoryUow()
    await _user(uow, 7)
    first = await _save(uow)
    second = await _save(uow)
    assert first.title.startswith(f"{program_type_label(ProgramType.FULL_BODY)} · 1 день · ")
    assert second.title == f"{first.title} (2)"

    listed = await ListProgramCatalogQueryHandler(uow).handle(ListProgramCatalogQuery(telegram_user_id=7))
    assert len({item.title for item in listed.items}) == 2


async def test_rename_card_and_reject_foreign_card() -> None:
    uow = InMemoryUow()
    await _user(uow, 7)
    await _user(uow, 8)
    saved = await _save(uow)

    renamed = await RenameLibraryProgramCommandHandler(uow).handle(
        RenameLibraryProgramCommand(telegram_user_id=7, program_id=saved.program_id, title="Моя сила зима"),
    )
    assert renamed.title == "Моя сила зима"
    assert (await _card(uow, saved.program_id)).title == "Моя сила зима"

    with pytest.raises(DomainError):
        await RenameLibraryProgramCommandHandler(uow).handle(
            RenameLibraryProgramCommand(telegram_user_id=8, program_id=saved.program_id, title="Чужое"),
        )


async def test_edit_card_saves_into_card_without_touching_active_program() -> None:
    uow = InMemoryUow()
    await _user(uow, 7)
    saved = await _save(uow, title="База")
    # Make the card the active plan ("как у автора") — the card itself stays in the library.
    applied = await ApplyCatalogProgramCommandHandler(uow, ScriptedLanguageModel([]), _catalog()).handle(
        ApplyCatalogProgramCommand(telegram_user_id=7, program_id=saved.program_id, mode="as_is"),
    )
    active_id = applied.active_program_id
    assert active_id is not None

    draft = await ProposeLibraryProgramEditCommandHandler(
        uow,
        ScriptedLanguageModel([_edit_json(sets=5)]),
        _catalog(),
    ).handle(ProposeLibraryProgramEditCommand(telegram_user_id=7, program_id=saved.program_id, utterance="тягу"))
    assert draft.proposal_id is not None
    assert draft.document is not None

    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.library_program_id == saved.program_id
    assert approved.program_id is None

    card = await _card(uow, saved.program_id)
    assert card.status == ProgramStatus.DRAFT
    assert card.title == "База"
    assert card.days[0].slots[0].exercise_id == EX_B
    assert card.days[0].slots[0].sets == 5

    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(7)
        assert user is not None
        assert user.active_program_id == active_id
        assert user.pending_proposal_id is None
        active = await repos.programs.get_by_id(active_id)
    assert active is not None
    assert active.days[0].slots[0].exercise_id == EX_A


async def test_edit_published_card_keeps_code_and_new_claims_get_update() -> None:
    uow = InMemoryUow()
    await _user(uow, 7)
    await _user(uow, 8)
    saved = await _save(uow, title="Друзьям")
    published = await PublishProgramCommandHandler(uow).handle(
        PublishProgramCommand(telegram_user_id=7, program_id=saved.program_id),
    )

    await ProposeLibraryProgramEditCommandHandler(uow, ScriptedLanguageModel([_edit_json()]), _catalog()).handle(
        ProposeLibraryProgramEditCommand(telegram_user_id=7, program_id=saved.program_id, utterance="тягу"),
    )
    await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))

    card = await _card(uow, saved.program_id)
    assert card.status == ProgramStatus.PUBLISHED
    assert card.distribution_code == published.distribution_code

    claimed = await ClaimProgramByCodeCommandHandler(uow).handle(
        ClaimProgramByCodeCommand(telegram_user_id=8, code=published.distribution_code),
    )
    copy = await _card(uow, claimed.program_id)
    assert copy.days[0].slots[0].exercise_id == EX_B


async def test_delete_card_hides_it_and_unpublishes() -> None:
    uow = InMemoryUow()
    await _user(uow, 7)
    keep = await _save(uow, title="Оставить")
    drop = await _save(uow, title="Удалить")
    await PublishProgramCommandHandler(uow).handle(
        PublishProgramCommand(telegram_user_id=7, program_id=drop.program_id)
    )

    deleted = await DeleteLibraryProgramCommandHandler(uow).handle(
        DeleteLibraryProgramCommand(telegram_user_id=7, program_id=drop.program_id),
    )
    assert deleted.title == "Удалить"

    listed = await ListProgramCatalogQueryHandler(uow).handle(ListProgramCatalogQuery(telegram_user_id=7))
    assert [item.program_id for item in listed.items] == [keep.program_id]
    card = await _card(uow, drop.program_id)
    assert card.status == ProgramStatus.ARCHIVED
    assert card.distribution_code is None

    with pytest.raises(DomainError):
        await RenameLibraryProgramCommandHandler(uow).handle(
            RenameLibraryProgramCommand(telegram_user_id=7, program_id=drop.program_id, title="Снова"),
        )
