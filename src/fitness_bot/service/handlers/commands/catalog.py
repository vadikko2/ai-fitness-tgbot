from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import cqrs

from fitness_bot.domain.enums import ExpectedInput, ProgramStatus, ProposalKind
from fitness_bot.domain.errors import AgentUnavailable, DomainError, InvalidWorkoutDocument
from fitness_bot.domain.users.user import User
from fitness_bot.domain.workout.program import (
    Program,
    default_library_title,
    normalize_library_title,
    unique_library_title,
)
from fitness_bot.domain.workout.proposal import Proposal
from fitness_bot.service.authz import require_coach_of
from fitness_bot.service.handlers.commands.agent_json import (
    catalog_json,
    clip_reply,
    complete_json,
    document_json,
    parse_workout_document,
    reply_from_payload,
    workout_document_schema_json,
)
from fitness_bot.service.handlers.commands.program import _replace_pending, build_profile_payload
from fitness_bot.service.handlers.commands.wellbeing_context import link_wellbeing_to_proposal, load_wellbeing_context
from fitness_bot.service.interfaces.uow import IUow, IUowRepositories
from fitness_bot.service.models.commands import catalog as cmds
from fitness_bot.service.ports.language_model import LanguageModel
from fitness_bot.service.ports.video_search import ExerciseCatalogReader


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


logger = logging.getLogger(__name__)

_LIBRARY_TITLE_SCAN_LIMIT = 200


async def _require_library_card(repos: IUowRepositories, user: User, program_id: UUID) -> Program:
    card = await repos.programs.get_by_id(program_id)
    if card is None or card.user_id != user.id or not card.is_library_card:
        raise DomainError("library program not found")
    return card


async def _taken_library_titles(repos: IUowRepositories, user: User, *, exclude: UUID | None = None) -> set[str]:
    cards = await repos.programs.list_catalog_for_user(user.id, limit=_LIBRARY_TITLE_SCAN_LIMIT)
    return {card.display_title() for card in cards if card.id != exclude}


def _normalize_code(raw: str) -> str:
    text = raw.strip()
    if text.startswith("p_") or text.startswith("P_"):
        text = text[2:]
    return text.upper()


class SaveProgramDraftCommandHandler(
    cqrs.RequestHandler[cmds.SaveProgramDraftCommand, cmds.SaveProgramDraftCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.SaveProgramDraftCommand) -> cmds.SaveProgramDraftCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if request.title and request.title.strip():
                title = normalize_library_title(request.title)
            else:
                title = unique_library_title(
                    default_library_title(request.document),
                    await _taken_library_titles(repos, user),
                )
            draft = Program.draft_from_document(
                user_id=user.id,
                document=request.document,
                title=title,
                author_label=request.author_label or user.public_label(),
            )
            saved = await repos.programs.add(draft)
            return cmds.SaveProgramDraftCommandResult(
                program_id=saved.id,
                status=saved.status,
                title=saved.display_title(),
            )


class RenameLibraryProgramCommandHandler(
    cqrs.RequestHandler[cmds.RenameLibraryProgramCommand, cmds.RenameLibraryProgramCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.RenameLibraryProgramCommand) -> cmds.RenameLibraryProgramCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            card = await _require_library_card(repos, user, request.program_id)
            card.rename(request.title)
            saved = await repos.programs.save(card)
            user.clear_expectation()
            await repos.users.save(user)
            return cmds.RenameLibraryProgramCommandResult(program_id=saved.id, title=saved.display_title())


class DeleteLibraryProgramCommandHandler(
    cqrs.RequestHandler[cmds.DeleteLibraryProgramCommand, cmds.DeleteLibraryProgramCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.DeleteLibraryProgramCommand) -> cmds.DeleteLibraryProgramCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            card = await _require_library_card(repos, user, request.program_id)
            title = card.display_title()
            pending = await repos.proposals.get_pending_for_user(user.id)
            if pending is not None and pending.base_program_id == card.id:
                pending.discard()
                await repos.proposals.save(pending)
                user.pending_proposal_id = None
                user.clear_expectation()
                await repos.users.save(user)
            card.remove_from_library()
            await repos.programs.save(card)
            return cmds.DeleteLibraryProgramCommandResult(program_id=card.id, title=title)


class ProposeLibraryProgramEditCommandHandler(
    cqrs.RequestHandler[cmds.ProposeLibraryProgramEditCommand, cmds.ProposeLibraryProgramEditCommandResult],
):
    """Draft an edit of a library card; approving it saves into the card, not the active plan."""

    def __init__(self, uow: IUow, language_model: LanguageModel, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._language_model = language_model
        self._catalog = catalog

    async def handle(
        self,
        request: cmds.ProposeLibraryProgramEditCommand,
    ) -> cmds.ProposeLibraryProgramEditCommandResult:
        from fitness_bot.service.handlers.commands.program import _load_catalog_ids

        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            card = await _require_library_card(repos, user, request.program_id)
            pending = await repos.proposals.get_pending_for_user(user.id)
            continuing = (
                pending is not None
                and pending.kind == ProposalKind.PROGRAM
                and pending.base_program_id == card.id
                and pending.document is not None
            )
            current = pending.document if continuing and pending is not None else card.to_document()
            assert current is not None
            records, allowed = await _load_catalog_ids(self._catalog, training_place=user.training_place)

            payload = None
            try:
                payload = await complete_json(
                    self._language_model,
                    prompt_name="workout_editor.md",
                    prompt_context={
                        "document_json": document_json(current),
                        "utterance": request.utterance,
                        "limitations": user.limitations or "",
                        "training_place": user.training_place.value if user.training_place else "",
                        "catalog_json": catalog_json(records),
                        "schema_json": workout_document_schema_json(),
                        "focus_day_position": None,
                    },
                )
            except AgentUnavailable:
                return cmds.ProposeLibraryProgramEditCommandResult(program_id=card.id, agent_unavailable=True)

            try:
                document_raw = payload.get("document")
                if not isinstance(document_raw, dict):
                    raise InvalidWorkoutDocument("response.document must be an object")
                document = parse_workout_document(document_raw, default_program_type=current.program_type)
                document = document.model_copy(update={"program_type": current.program_type})
                document.assert_catalog_ids(allowed)
                document.assert_schedule_complete()
                reply = clip_reply(payload.get("reply"))
            except (InvalidWorkoutDocument, ValueError, TypeError, KeyError) as exc:
                logger.warning("library edit schema failed: %s", exc)
                return cmds.ProposeLibraryProgramEditCommandResult(
                    program_id=card.id,
                    schema_failed=True,
                    reply=reply_from_payload(payload),
                )

            if continuing and pending is not None:
                pending.replace_document(document, reply=reply)
                saved = await repos.proposals.save(pending)
            else:
                proposal = Proposal.new_program_document(
                    user_id=user.id,
                    program_type=document.program_type,
                    document=document,
                    reply=reply,
                    base_program_id=card.id,
                )
                saved = await _replace_pending(repos, user, proposal)
            user.expect_input(ExpectedInput.PROPOSAL_UTTERANCE, expected_field=f"library_edit:{card.id}")
            user.pending_proposal_id = saved.id
            await repos.users.save(user)
            return cmds.ProposeLibraryProgramEditCommandResult(
                proposal_id=saved.id,
                program_id=card.id,
                reply=reply,
                document=document,
            )


class PublishProgramCommandHandler(
    cqrs.RequestHandler[cmds.PublishProgramCommand, cmds.PublishProgramCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.PublishProgramCommand) -> cmds.PublishProgramCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            program = await repos.programs.get_by_id(request.program_id)
            if program is None or program.user_id != user.id:
                raise DomainError("program not found")
            if program.author_label is None:
                program.author_label = user.public_label()
            saved = await repos.programs.publish(program)
            return cmds.PublishProgramCommandResult(
                program_id=saved.id,
                distribution_code=saved.distribution_code or "",
                title=saved.display_title(),
            )


class UnpublishProgramCommandHandler(
    cqrs.RequestHandler[cmds.UnpublishProgramCommand, cmds.UnpublishProgramCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.UnpublishProgramCommand) -> cmds.UnpublishProgramCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            program = await repos.programs.get_by_id(request.program_id)
            if program is None or program.user_id != user.id:
                raise DomainError("program not found")
            saved = await repos.programs.unpublish(program)
            return cmds.UnpublishProgramCommandResult(program_id=saved.id)


class ClaimProgramByCodeCommandHandler(
    cqrs.RequestHandler[cmds.ClaimProgramByCodeCommand, cmds.ClaimProgramByCodeCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.ClaimProgramByCodeCommand) -> cmds.ClaimProgramByCodeCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            source = await repos.programs.get_by_distribution_code(_normalize_code(request.code))
            if source is None:
                raise DomainError("published program not found")
            existing = await repos.programs.find_existing_claim(user_id=user.id, source_program_id=source.id)
            if existing is not None:
                return cmds.ClaimProgramByCodeCommandResult(
                    program_id=existing.id,
                    title=existing.display_title(),
                    already_claimed=True,
                    author_label=existing.author_label,
                    source_program_id=source.id,
                )
            author = await repos.users.get_by_id(source.user_id)
            copy = source.claim_copy_for(
                claimant_user_id=user.id,
                author_label=source.author_label or (author.public_label() if author else None),
            )
            saved = await repos.programs.add(copy)
            return cmds.ClaimProgramByCodeCommandResult(
                program_id=saved.id,
                title=saved.display_title(),
                author_label=saved.author_label,
                source_program_id=source.id,
            )


class ApplyCatalogProgramCommandHandler(
    cqrs.RequestHandler[cmds.ApplyCatalogProgramCommand, cmds.ApplyCatalogProgramCommandResult],
):
    def __init__(self, uow: IUow, language_model: LanguageModel, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._language_model = language_model
        self._catalog = catalog

    async def handle(self, request: cmds.ApplyCatalogProgramCommand) -> cmds.ApplyCatalogProgramCommandResult:
        mode = request.mode.strip().lower()
        if mode not in {"adapt", "as_is"}:
            raise DomainError("mode must be adapt or as_is")
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            card = await repos.programs.get_by_id(request.program_id)
            if card is None or card.user_id != user.id:
                raise DomainError("catalog program not found")
            if card.status not in {ProgramStatus.DRAFT, ProgramStatus.PUBLISHED}:
                raise DomainError("only library cards can be applied")
            document = card.to_document()
            if mode == "as_is":
                document.assert_approvable()
                now = datetime.now(UTC)
                if user.active_program_id is not None:
                    current = await repos.programs.get_by_id(user.active_program_id)
                    if current is not None and current.status == ProgramStatus.ACTIVE:
                        current.archive(now=now)
                        await repos.programs.save(current)
                active = Program.from_approved_document(
                    user_id=user.id,
                    document=document,
                    now=now,
                    title=card.display_title(),
                    author_label=card.author_label,
                    source_program_id=card.source_program_id or card.id,
                    source_author_user_id=card.source_author_user_id or card.user_id,
                )
                saved = await repos.programs.add(active)
                user.active_program_id = saved.id
                user.nutrition_stale = True
                user.clear_expectation()
                await repos.users.save(user)
                return cmds.ApplyCatalogProgramCommandResult(
                    active_program_id=saved.id,
                    mode=mode,
                    document=document,
                )

            profile = await build_profile_payload(repos, user)
            import json

            from fitness_bot.service.handlers.commands.agent_json import (
                catalog_json,
                document_json,
                workout_document_schema_json,
            )
            from fitness_bot.service.handlers.commands.program import _load_catalog_ids

            records, _ = await _load_catalog_ids(
                self._catalog,
                training_place=user.training_place,
            )
            wellbeing = await load_wellbeing_context(repos, user.id)
            payload = await complete_json(
                self._language_model,
                prompt_name="workout_editor.md",
                prompt_context={
                    "document_json": document_json(document),
                    "utterance": request.utterance or "адаптируй программу под мой профиль: нагрузки и объём",
                    "limitations": user.limitations or "",
                    "training_place": user.training_place.value if user.training_place else "",
                    "catalog_json": catalog_json(records),
                    "schema_json": workout_document_schema_json(),
                    "focus_day_position": None,
                    "profile_json": json.dumps(profile, ensure_ascii=False),
                    **wellbeing.prompt_context(),
                },
            )
            adapted = parse_workout_document(payload, default_program_type=document.program_type)
            reply = clip_reply(payload.get("reply"))
            adapt_diff = clip_reply(payload.get("adapt_diff") or reply)
            proposal = Proposal.new_program_document(
                user_id=user.id,
                program_type=adapted.program_type,
                document=adapted,
                reply=reply,
                base_program_id=user.active_program_id,
            )
            saved = await _replace_pending(repos, user, proposal)
            await link_wellbeing_to_proposal(repos, wellbeing, saved.id)
            user.expect_input(ExpectedInput.PROPOSAL_UTTERANCE, expected_field="program_edit")
            user.pending_proposal_id = saved.id
            await repos.users.save(user)
            return cmds.ApplyCatalogProgramCommandResult(
                proposal_id=saved.id,
                mode=mode,
                reply=reply,
                document=adapted,
                adapt_diff=adapt_diff,
            )


class AssignProgramToClientCommandHandler(
    cqrs.RequestHandler[cmds.AssignProgramToClientCommand, cmds.AssignProgramToClientCommandResult],
):
    def __init__(
        self,
        uow: IUow,
        language_model: LanguageModel | None = None,
        catalog: ExerciseCatalogReader | None = None,
    ) -> None:
        self._uow = uow
        self._language_model = language_model
        self._catalog = catalog

    async def handle(self, request: cmds.AssignProgramToClientCommand) -> cmds.AssignProgramToClientCommandResult:
        mode = request.mode.strip().lower()
        if mode not in {"adapt", "as_is"}:
            raise DomainError("mode must be adapt or as_is")
        async with self._uow.transaction() as repos:
            coach = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            await require_coach_of(repos, coach, request.client_user_id)
            client = _require_user(await repos.users.get_by_id(request.client_user_id))
            source = await repos.programs.get_by_id(request.program_id)
            if source is None or source.user_id != coach.id:
                raise DomainError("program not found in coach library")
            document = source.to_document()
            if mode == "adapt" and self._language_model is not None and self._catalog is not None:
                import json

                from fitness_bot.service.handlers.commands.agent_json import (
                    catalog_json,
                    document_json,
                    workout_document_schema_json,
                )
                from fitness_bot.service.handlers.commands.program import _load_catalog_ids

                profile = await build_profile_payload(repos, client)
                records, _ = await _load_catalog_ids(
                    self._catalog,
                    training_place=client.training_place,
                )
                payload = await complete_json(
                    self._language_model,
                    prompt_name="workout_editor.md",
                    prompt_context={
                        "document_json": document_json(document),
                        "utterance": "адаптируй программу под профиль клиента",
                        "limitations": client.limitations or "",
                        "training_place": client.training_place.value if client.training_place else "",
                        "catalog_json": catalog_json(records),
                        "schema_json": workout_document_schema_json(),
                        "focus_day_position": None,
                        "profile_json": json.dumps(profile, ensure_ascii=False),
                    },
                )
                document = parse_workout_document(payload, default_program_type=document.program_type)
            document.assert_approvable()
            now = datetime.now(UTC)
            if client.active_program_id is not None:
                current = await repos.programs.get_by_id(client.active_program_id)
                if current is not None and current.status == ProgramStatus.ACTIVE:
                    current.archive(now=now)
                    await repos.programs.save(current)
            active = Program.from_approved_document(
                user_id=client.id,
                document=document,
                now=now,
                title=source.display_title(),
                assigned_by_user_id=coach.id,
                author_label=coach.public_label(),
                source_program_id=source.id,
                source_author_user_id=coach.id,
            )
            saved = await repos.programs.add(active)
            client.active_program_id = saved.id
            client.nutrition_stale = True
            await repos.users.save(client)
            return cmds.AssignProgramToClientCommandResult(
                active_program_id=saved.id,
                client_user_id=client.id,
                client_chat_id=client.chat_id,
                title=saved.display_title(),
            )
