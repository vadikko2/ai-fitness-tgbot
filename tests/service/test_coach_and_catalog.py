from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from fitness_bot.domain.enums import ProgramStatus, ProgramType, TrainingStyle, WorkoutIntensity
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay, WorkoutDocument
from fitness_bot.domain.workout.program import Program
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.authz import AuthorizationError, require_moderator
from fitness_bot.service.handlers.commands.catalog import (
    ClaimProgramByCodeCommandHandler,
    PublishProgramCommandHandler,
    SaveProgramDraftCommandHandler,
)
from fitness_bot.service.handlers.commands.coach import (
    AcceptCoachInviteCommandHandler,
    ApproveCoachApplicationCommandHandler,
    CreateCoachInviteCommandHandler,
    GrantModeratorCommandHandler,
    RejectCoachApplicationCommandHandler,
    RevokeModeratorCommandHandler,
    SubmitCoachApplicationCommandHandler,
    SyncUserIdentityCommandHandler,
    UnlinkCoachClientCommandHandler,
)
from fitness_bot.service.handlers.commands.users import EnsureUserCommandHandler
from fitness_bot.service.handlers.queries.coach import (
    CountActiveClientsForCoachQueryHandler,
    GetMyCoachApplicationQueryHandler,
    ListMyCoachApplicationsQueryHandler,
)
from fitness_bot.service.handlers.queries.users import GetHomeQueryHandler
from fitness_bot.service.models.commands.catalog import (
    ClaimProgramByCodeCommand,
    PublishProgramCommand,
    SaveProgramDraftCommand,
)
from fitness_bot.service.models.commands.coach import (
    AcceptCoachInviteCommand,
    ApproveCoachApplicationCommand,
    CreateCoachInviteCommand,
    GrantModeratorCommand,
    RejectCoachApplicationCommand,
    RevokeModeratorCommand,
    SubmitCoachApplicationCommand,
    SyncUserIdentityCommand,
    UnlinkCoachClientCommand,
)
from fitness_bot.service.models.commands.users import EnsureUserCommand
from fitness_bot.service.models.queries.coach import (
    CountActiveClientsForCoachQuery,
    GetMyCoachApplicationQuery,
    ListMyCoachApplicationsQuery,
)
from fitness_bot.service.models.queries.users import GetHomeQuery


def _doc() -> WorkoutDocument:
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
                    ExerciseSlot(
                        position=1,
                        exercise_id=uuid4(),
                        sets=3,
                        reps=10,
                        rest_seconds=90,
                        rpe=7,
                    ),
                ],
            ),
        ],
    )


async def _user(uow: InMemoryUow, telegram_id: int, *, moderator: bool = False):
    await EnsureUserCommandHandler(uow).handle(
        EnsureUserCommand(telegram_user_id=telegram_id, chat_id=telegram_id),
    )
    await SyncUserIdentityCommandHandler(uow).handle(
        SyncUserIdentityCommand(
            telegram_user_id=telegram_id,
            chat_id=telegram_id,
            display_name=f"User {telegram_id}",
            telegram_username=f"u{telegram_id}",
            bootstrap_moderator_ids=[telegram_id] if moderator else [],
        ),
    )
    async with uow.transaction() as repos:
        return await repos.users.get_by_telegram_id(telegram_id)


@pytest.mark.asyncio
async def test_moderator_bootstrap_and_grant_revoke() -> None:
    uow = InMemoryUow()
    mod = await _user(uow, 100, moderator=True)
    assert mod is not None and mod.is_moderator
    require_moderator(mod)

    await _user(uow, 200)
    await GrantModeratorCommandHandler(uow).handle(
        GrantModeratorCommand(actor_telegram_user_id=100, target_telegram_user_id=200),
    )
    async with uow.transaction() as repos:
        other = await repos.users.get_by_telegram_id(200)
        assert other is not None and other.is_moderator

    await RevokeModeratorCommandHandler(uow).handle(
        RevokeModeratorCommand(actor_telegram_user_id=100, target_telegram_user_id=200),
    )
    with pytest.raises(DomainError, match="last moderator"):
        await RevokeModeratorCommandHandler(uow).handle(
            RevokeModeratorCommand(actor_telegram_user_id=100, target_telegram_user_id=100),
        )


@pytest.mark.asyncio
async def test_application_approve_reject_race() -> None:
    uow = InMemoryUow()
    await _user(uow, 1, moderator=True)
    await _user(uow, 2, moderator=True)
    applicant = await _user(uow, 3)
    assert applicant is not None

    submitted = await SubmitCoachApplicationCommandHandler(uow).handle(
        SubmitCoachApplicationCommand(
            telegram_user_id=3,
            display_name="Coach",
            bio="bio",
            portfolio_url="https://example.com",
            credential_object_key="users/x/cred",
            credential_content_type="image/png",
            credential_byte_size=10,
        ),
    )
    first = await ApproveCoachApplicationCommandHandler(uow).handle(
        ApproveCoachApplicationCommand(telegram_user_id=1, application_id=submitted.application_id),
    )
    assert first.already_processed is False
    second = await ApproveCoachApplicationCommandHandler(uow).handle(
        ApproveCoachApplicationCommand(telegram_user_id=2, application_id=submitted.application_id),
    )
    assert second.already_processed is True

    await _user(uow, 4)
    submitted2 = await SubmitCoachApplicationCommandHandler(uow).handle(
        SubmitCoachApplicationCommand(
            telegram_user_id=4,
            display_name="Coach2",
            bio="bio",
            portfolio_url="https://example.com",
            credential_object_key="users/y/cred",
            credential_content_type="image/png",
            credential_byte_size=10,
        ),
    )
    with pytest.raises(DomainError, match="comment"):
        await RejectCoachApplicationCommandHandler(uow).handle(
            RejectCoachApplicationCommand(
                telegram_user_id=1,
                application_id=submitted2.application_id,
                comment="  ",
            ),
        )
    rejected = await RejectCoachApplicationCommandHandler(uow).handle(
        RejectCoachApplicationCommand(
            telegram_user_id=1,
            application_id=submitted2.application_id,
            comment="недостаточно",
        ),
    )
    assert rejected.already_processed is False


@pytest.mark.asyncio
async def test_invite_accept_unlink_and_home_badge() -> None:
    uow = InMemoryUow()
    await _user(uow, 10, moderator=True)
    coach = await _user(uow, 11)
    client = await _user(uow, 12)
    assert coach and client

    await SubmitCoachApplicationCommandHandler(uow).handle(
        SubmitCoachApplicationCommand(
            telegram_user_id=11,
            display_name="Coach",
            bio="bio",
            portfolio_url="https://example.com",
            credential_object_key="k",
            credential_content_type="image/png",
            credential_byte_size=1,
        ),
    )
    async with uow.transaction() as repos:
        apps = await repos.coaches.list_pending_applications()
        app_id = apps[0].id
    await ApproveCoachApplicationCommandHandler(uow).handle(
        ApproveCoachApplicationCommand(telegram_user_id=10, application_id=app_id),
    )

    with pytest.raises(AuthorizationError):
        await CreateCoachInviteCommandHandler(uow).handle(CreateCoachInviteCommand(telegram_user_id=12))

    invite = await CreateCoachInviteCommandHandler(uow).handle(CreateCoachInviteCommand(telegram_user_id=11))
    accepted = await AcceptCoachInviteCommandHandler(uow).handle(
        AcceptCoachInviteCommand(telegram_user_id=12, code=invite.code),
    )
    count = await CountActiveClientsForCoachQueryHandler(uow).handle(
        CountActiveClientsForCoachQuery(telegram_user_id=11),
    )
    assert count.count == 1
    home = await GetHomeQueryHandler(uow).handle(GetHomeQuery(telegram_user_id=11))
    assert home.show_coach_badge and home.active_clients_count == 1

    await UnlinkCoachClientCommandHandler(uow).handle(
        UnlinkCoachClientCommand(telegram_user_id=12, link_id=accepted.link_id),
    )
    count2 = await CountActiveClientsForCoachQueryHandler(uow).handle(
        CountActiveClientsForCoachQuery(telegram_user_id=11),
    )
    assert count2.count == 0


@pytest.mark.asyncio
async def test_publish_claim_no_duplicate() -> None:
    uow = InMemoryUow()
    await _user(uow, 20, moderator=True)
    await _user(uow, 21)
    await _user(uow, 22)

    await SubmitCoachApplicationCommandHandler(uow).handle(
        SubmitCoachApplicationCommand(
            telegram_user_id=21,
            display_name="Author",
            bio="bio",
            portfolio_url="https://example.com",
            credential_object_key="k",
            credential_content_type="image/png",
            credential_byte_size=1,
        ),
    )
    async with uow.transaction() as repos:
        app_id = (await repos.coaches.list_pending_applications())[0].id
    await ApproveCoachApplicationCommandHandler(uow).handle(
        ApproveCoachApplicationCommand(telegram_user_id=20, application_id=app_id),
    )

    draft = await SaveProgramDraftCommandHandler(uow).handle(
        SaveProgramDraftCommand(telegram_user_id=21, document=_doc(), title="Авторский"),
    )
    published = await PublishProgramCommandHandler(uow).handle(
        PublishProgramCommand(telegram_user_id=21, program_id=draft.program_id),
    )
    assert published.distribution_code

    first = await ClaimProgramByCodeCommandHandler(uow).handle(
        ClaimProgramByCodeCommand(telegram_user_id=22, code=published.distribution_code),
    )
    second = await ClaimProgramByCodeCommandHandler(uow).handle(
        ClaimProgramByCodeCommand(telegram_user_id=22, code=f"p_{published.distribution_code}"),
    )
    assert first.program_id == second.program_id
    assert second.already_claimed is True
    async with uow.transaction() as repos:
        card = await repos.programs.get_by_id(first.program_id)
        assert card is not None
        assert card.status == ProgramStatus.DRAFT


@pytest.mark.asyncio
async def test_self_link_invite_rejected() -> None:
    uow = InMemoryUow()
    await _user(uow, 30, moderator=True)
    await _user(uow, 31)
    await SubmitCoachApplicationCommandHandler(uow).handle(
        SubmitCoachApplicationCommand(
            telegram_user_id=31,
            display_name="C",
            bio="b",
            portfolio_url="https://x",
            credential_object_key="k",
            credential_content_type="image/png",
            credential_byte_size=1,
        ),
    )
    async with uow.transaction() as repos:
        app_id = (await repos.coaches.list_pending_applications())[0].id
    await ApproveCoachApplicationCommandHandler(uow).handle(
        ApproveCoachApplicationCommand(telegram_user_id=30, application_id=app_id),
    )
    invite = await CreateCoachInviteCommandHandler(uow).handle(CreateCoachInviteCommand(telegram_user_id=31))
    with pytest.raises(DomainError, match="yourself"):
        await AcceptCoachInviteCommandHandler(uow).handle(
            AcceptCoachInviteCommand(telegram_user_id=31, code=invite.code),
        )


@pytest.mark.asyncio
async def test_application_returns_moderator_message_refs_after_record() -> None:
    uow = InMemoryUow()
    mod1 = await _user(uow, 40, moderator=True)
    mod2 = await _user(uow, 41, moderator=True)
    await _user(uow, 42)
    assert mod1 and mod2

    submitted = await SubmitCoachApplicationCommandHandler(uow).handle(
        SubmitCoachApplicationCommand(
            telegram_user_id=42,
            display_name="Coach",
            bio="bio",
            portfolio_url="https://example.com",
            credential_object_key="k",
            credential_content_type="image/png",
            credential_byte_size=1,
        ),
    )
    assert len(submitted.moderator_chats) >= 2
    from fitness_bot.service.handlers.commands.coach import RecordModeratorApplicationMessageCommandHandler
    from fitness_bot.service.models.commands.coach import RecordModeratorApplicationMessageCommand

    for idx, chat in enumerate(submitted.moderator_chats):
        await RecordModeratorApplicationMessageCommandHandler(uow).handle(
            RecordModeratorApplicationMessageCommand(
                application_id=submitted.application_id,
                moderator_user_id=UUID(chat["user_id"]),
                chat_id=int(chat["chat_id"]),
                message_id=1000 + idx,
            ),
        )
    approved = await ApproveCoachApplicationCommandHandler(uow).handle(
        ApproveCoachApplicationCommand(telegram_user_id=40, application_id=submitted.application_id),
    )
    assert approved.already_processed is False
    assert len(approved.moderator_message_refs) == 2
    assert approved.status_text.startswith("✅")
    assert approved.applicant_chat_id == 42


@pytest.mark.asyncio
async def test_coach_live_edit_client_program_approve_push_fields() -> None:
    import json

    from fitness_bot.domain.enums import ExpectedInput
    from fitness_bot.service.handlers.commands.coach import StartCoachClientProgramEditCommandHandler
    from fitness_bot.service.handlers.commands.program import (
        ApproveProposalCommandHandler,
        ProposeProgramChangeCommandHandler,
    )
    from fitness_bot.service.models.commands.coach import StartCoachClientProgramEditCommand
    from fitness_bot.service.models.commands.program import ApproveProposalCommand, ProposeProgramChangeCommand
    from fitness_bot.service.ports.exercise_catalog import InMemoryExerciseCatalog, record

    uow = InMemoryUow()
    await _user(uow, 50, moderator=True)
    coach = await _user(uow, 51)
    client = await _user(uow, 52)
    assert coach and client

    await SubmitCoachApplicationCommandHandler(uow).handle(
        SubmitCoachApplicationCommand(
            telegram_user_id=51,
            display_name="Coach",
            bio="bio",
            portfolio_url="https://example.com",
            credential_object_key="k",
            credential_content_type="image/png",
            credential_byte_size=1,
        ),
    )
    async with uow.transaction() as repos:
        app_id = (await repos.coaches.list_pending_applications())[0].id
    await ApproveCoachApplicationCommandHandler(uow).handle(
        ApproveCoachApplicationCommand(telegram_user_id=50, application_id=app_id),
    )
    invite = await CreateCoachInviteCommandHandler(uow).handle(CreateCoachInviteCommand(telegram_user_id=51))
    await AcceptCoachInviteCommandHandler(uow).handle(
        AcceptCoachInviteCommand(telegram_user_id=52, code=invite.code),
    )

    ex_id = uuid4()
    doc = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="A",
                position=1,
                intensity=WorkoutIntensity.MEDIUM,
                training_style=TrainingStyle.CLASSIC,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=ex_id,
                        sets=3,
                        reps=10,
                        rest_seconds=90,
                        rpe=7,
                    ),
                ],
            ),
        ],
    )
    async with uow.transaction() as repos:
        program = Program.from_approved_document(user_id=client.id, document=doc, title="Клиентский")
        saved = await repos.programs.add(program)
        client.active_program_id = saved.id
        await repos.users.save(client)

    started = await StartCoachClientProgramEditCommandHandler(uow).handle(
        StartCoachClientProgramEditCommand(telegram_user_id=51, client_user_id=client.id),
    )
    assert started.has_active_program is True
    async with uow.transaction() as repos:
        coach_fresh = await repos.users.get_by_telegram_id(51)
        assert coach_fresh is not None
        assert coach_fresh.expected_input == ExpectedInput.COACH_EDIT_CLIENT
        assert coach_fresh.expected_field == str(client.id)

    catalog = InMemoryExerciseCatalog(exercises=[record(exercise_id=ex_id, name="Жим", primary_muscles=["грудь"])])

    class _LM:
        async def complete(self, *, system: str, user: str) -> str:
            _ = system, user
            return json.dumps(
                {
                    "reply": "ок",
                    "document": {
                        "program_type": "full_body",
                        "days": [
                            {
                                "weekday": 2,
                                "title": "B",
                                "position": 1,
                                "intensity": "medium",
                                "training_style": "classic",
                                "slots": [
                                    {
                                        "position": 1,
                                        "exercise_id": str(ex_id),
                                        "sets": 4,
                                        "reps": 8,
                                        "rest_seconds": 90,
                                        "rpe": 7,
                                    },
                                ],
                            },
                        ],
                    },
                },
                ensure_ascii=False,
            )

    changed = await ProposeProgramChangeCommandHandler(uow, _LM(), catalog).handle(
        ProposeProgramChangeCommand(
            telegram_user_id=51,
            utterance="сделай во вторник 4 подхода",
            subject_user_id=client.id,
        ),
    )
    assert changed.document is not None
    assert changed.subject_user_id == client.id

    approved = await ApproveProposalCommandHandler(uow).handle(
        ApproveProposalCommand(telegram_user_id=51, subject_user_id=client.id),
    )
    assert approved.program_id is not None
    assert approved.client_chat_id == 52
    assert approved.program_title
    async with uow.transaction() as repos:
        client_fresh = await repos.users.get_by_id(client.id)
        assert client_fresh is not None
        assert client_fresh.active_program_id == approved.program_id
        coach_fresh = await repos.users.get_by_telegram_id(51)
        assert coach_fresh is not None
        assert coach_fresh.expected_input == ExpectedInput.NONE


def test_domain_program_publish_requires_approvable() -> None:
    program = Program.draft_from_document(
        user_id=uuid4(),
        document=WorkoutDocument(program_type=ProgramType.FULL_BODY, days=[]),
        title="x",
    )
    with pytest.raises(Exception):
        program.publish()


@pytest.mark.asyncio
async def test_list_and_get_my_coach_applications() -> None:
    from fitness_bot.domain.enums import CoachApplicationStatus

    uow = InMemoryUow()
    await _user(uow, 70, moderator=True)
    await _user(uow, 71)
    await _user(uow, 72)

    submitted = await SubmitCoachApplicationCommandHandler(uow).handle(
        SubmitCoachApplicationCommand(
            telegram_user_id=71,
            display_name="Alice Coach",
            bio="bio",
            portfolio_url="https://example.com/a",
            credential_object_key="k1",
            credential_content_type="image/png",
            credential_byte_size=1,
        ),
    )
    await RejectCoachApplicationCommandHandler(uow).handle(
        RejectCoachApplicationCommand(
            telegram_user_id=70,
            application_id=submitted.application_id,
            comment="Недостаточно документов",
        ),
    )
    pending = await SubmitCoachApplicationCommandHandler(uow).handle(
        SubmitCoachApplicationCommand(
            telegram_user_id=71,
            display_name="Alice Coach",
            bio="bio2",
            portfolio_url="https://example.com/a2",
            credential_object_key="k2",
            credential_content_type="image/png",
            credential_byte_size=1,
        ),
    )

    mine = await ListMyCoachApplicationsQueryHandler(uow).handle(
        ListMyCoachApplicationsQuery(telegram_user_id=71),
    )
    assert len(mine.items) == 2
    assert mine.items[0].application_id == pending.application_id
    assert mine.items[0].status == CoachApplicationStatus.PENDING
    assert mine.items[1].status == CoachApplicationStatus.REJECTED

    other = await ListMyCoachApplicationsQueryHandler(uow).handle(
        ListMyCoachApplicationsQuery(telegram_user_id=72),
    )
    assert other.items == []

    detail = await GetMyCoachApplicationQueryHandler(uow).handle(
        GetMyCoachApplicationQuery(telegram_user_id=71, application_id=submitted.application_id),
    )
    assert detail.status == CoachApplicationStatus.REJECTED
    assert detail.moderator_comment == "Недостаточно документов"

    with pytest.raises(DomainError, match="application not found"):
        await GetMyCoachApplicationQueryHandler(uow).handle(
            GetMyCoachApplicationQuery(telegram_user_id=72, application_id=submitted.application_id),
        )
