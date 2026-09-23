from __future__ import annotations

from datetime import UTC, datetime

import cqrs

from fitness_bot.domain.enums import ExpectedInput, ProposalKind, SessionStatus
from fitness_bot.domain.errors import AgentUnavailable, DomainError, InvalidWorkoutDocument
from fitness_bot.domain.users.user import User, local_calendar_date
from fitness_bot.domain.workout.document import SlotActual, WorkoutDocument
from fitness_bot.domain.workout.proposal import Proposal
from fitness_bot.domain.workout.session import Session
from fitness_bot.domain.workout.technique_video import MAX_TECHNIQUE_VIDEO_BYTES, TechniqueVideo
from fitness_bot.service.handlers.commands.agent_json import (
    catalog_json,
    clip_reply,
    complete_json,
    document_json,
    parse_slot,
    parse_workout_document,
    reply_from_payload,
    slot_json,
    workout_document_schema_json,
)
from fitness_bot.service.handlers.commands.program import _load_catalog_ids, _replace_pending
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.commands import session as cmds
from fitness_bot.service.ports.language_model import LanguageModel
from fitness_bot.service.ports.object_storage import ObjectStorage
from fitness_bot.service.ports.video_search import ExerciseCatalogReader


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


def _completed_on_local_day(
    sessions: list[Session],
    *,
    local_day,
    timezone_offset: str | None,
) -> list[Session]:
    matched: list[Session] = []
    for session in sessions:
        if session.status != SessionStatus.COMPLETED or session.completed_at is None:
            continue
        completed_at = session.completed_at
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=UTC)
        if local_calendar_date(now=completed_at, timezone_offset=timezone_offset) == local_day:
            matched.append(session)
    return matched


class StartSessionFromTemplateCommandHandler(
    cqrs.RequestHandler[cmds.StartSessionFromTemplateCommand, cmds.StartSessionFromTemplateCommandResult],
):
    def __init__(self, uow: IUow, object_storage: ObjectStorage) -> None:
        self._uow = uow
        self._object_storage = object_storage

    async def handle(
        self,
        request: cmds.StartSessionFromTemplateCommand,
    ) -> cmds.StartSessionFromTemplateCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_session_id is not None:
                existing = await repos.sessions.get_by_id(user.active_session_id)
                if existing is not None and existing.is_open:
                    raise DomainError("an open session already exists")
            if user.active_program_id is None:
                raise DomainError("active program is required to start a session")
            program = await repos.programs.get_by_id(user.active_program_id)
            if program is None:
                raise DomainError("active program not found")

            today = local_calendar_date(now=datetime.now(UTC), timezone_offset=user.timezone_offset)
            weekday = today.isoweekday()
            template = next((day for day in program.days if day.weekday == weekday), None)
            if template is None:
                raise DomainError("today is not a training day in the active program")

            history = await repos.sessions.list_completed_for_user(user.id, limit=50)
            completed_today = _completed_on_local_day(
                history,
                local_day=today,
                timezone_offset=user.timezone_offset,
            )
            if program.activated_at is not None:
                activated_at = program.activated_at
                if activated_at.tzinfo is None:
                    activated_at = activated_at.replace(tzinfo=UTC)
                completed_today = [
                    session
                    for session in completed_today
                    if session.completed_at is not None
                    and (
                        session.completed_at
                        if session.completed_at.tzinfo is not None
                        else session.completed_at.replace(tzinfo=UTC)
                    )
                    >= activated_at
                ]
            if completed_today and not request.overwrite_completed:
                return cmds.StartSessionFromTemplateCommandResult(needs_repeat_confirmation=True)

            if completed_today and request.overwrite_completed:
                for old in completed_today:
                    videos = await repos.technique_videos.list_for_session(old.id)
                    for video in videos:
                        try:
                            await self._object_storage.delete(video.object_key)
                        except KeyError:
                            pass
                    pending = await repos.proposals.get_pending_for_user(user.id)
                    if pending is not None and pending.base_session_id == old.id:
                        pending.discard()
                        await repos.proposals.save(pending)
                    await repos.sessions.delete(old.id)

            session = Session.from_template_day(
                user_id=user.id,
                program_type=program.program_type,
                day=template,
            )
            saved = await repos.sessions.add(session)
            user.active_session_id = saved.id
            user.clear_expectation()
            await repos.users.save(user)
            return cmds.StartSessionFromTemplateCommandResult(
                session_id=saved.id,
                document=saved.to_document(),
            )


class ProposeWorkoutChangeCommandHandler(
    cqrs.RequestHandler[cmds.ProposeWorkoutChangeCommand, cmds.ProposeWorkoutChangeCommandResult],
):
    def __init__(self, uow: IUow, language_model: LanguageModel, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._language_model = language_model
        self._catalog = catalog

    async def handle(self, request: cmds.ProposeWorkoutChangeCommand) -> cmds.ProposeWorkoutChangeCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_session_id is None:
                raise DomainError("open session is required to edit a workout")
            session = await repos.sessions.get_by_id(user.active_session_id)
            if session is None or not session.is_open:
                raise DomainError("open session is required to edit a workout")
            if session.status != SessionStatus.IN_PROGRESS:
                raise DomainError("session can be edited only while in_progress")

            pending = await repos.proposals.get_pending_for_user(user.id)
            if (
                pending is not None
                and pending.kind == ProposalKind.WORKOUT_EDIT
                and pending.base_session_id == session.id
                and pending.document is not None
            ):
                current = pending.document
            else:
                current = session.to_document()

            records, allowed = await _load_catalog_ids(self._catalog)
            payload = None
            try:
                payload = await complete_json(
                    self._language_model,
                    prompt_name="workout_editor.md",
                    prompt_context={
                        "document_json": document_json(current),
                        "utterance": request.utterance,
                        "limitations": user.limitations or "",
                        "catalog_json": catalog_json(records),
                        "schema_json": workout_document_schema_json(),
                        "focus_day_position": current.days[0].position if current.days else 1,
                    },
                )
            except AgentUnavailable:
                return cmds.ProposeWorkoutChangeCommandResult(agent_unavailable=True)

            try:
                document_raw = payload.get("document")
                if not isinstance(document_raw, dict):
                    raise InvalidWorkoutDocument("response.document must be an object")
                document = parse_workout_document(document_raw, default_program_type=session.program_type)
                document = document.model_copy(update={"program_type": session.program_type})
                if len(document.days) != 1:
                    raise InvalidWorkoutDocument("session edit requires exactly one day")
                document.assert_catalog_ids(allowed)
                reply = clip_reply(payload.get("reply"))
            except (InvalidWorkoutDocument, ValueError, TypeError, KeyError):
                return cmds.ProposeWorkoutChangeCommandResult(
                    schema_failed=True,
                    reply=reply_from_payload(payload),
                )

            if (
                pending is not None
                and pending.kind == ProposalKind.WORKOUT_EDIT
                and pending.base_session_id == session.id
            ):
                pending.replace_document(document, reply=reply)
                saved = await repos.proposals.save(pending)
            else:
                proposal = Proposal.new_workout_edit(
                    user_id=user.id,
                    document=document,
                    base_session_id=session.id,
                    reply=reply,
                )
                saved = await _replace_pending(repos, user, proposal)

            user.expect_input(ExpectedInput.PROPOSAL_UTTERANCE, expected_field="workout_edit")
            user.pending_proposal_id = saved.id
            await repos.users.save(user)
            return cmds.ProposeWorkoutChangeCommandResult(
                proposal_id=saved.id,
                reply=reply,
                document=document,
            )


class ConfirmExerciseAsPlannedCommandHandler(
    cqrs.RequestHandler[cmds.ConfirmExerciseAsPlannedCommand, cmds.ConfirmExerciseAsPlannedCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.ConfirmExerciseAsPlannedCommand,
    ) -> cmds.ConfirmExerciseAsPlannedCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_session_id is None:
                raise DomainError("open session is required")
            session = await repos.sessions.get_by_id(user.active_session_id)
            if session is None or not session.is_open:
                raise DomainError("open session is required")
            slot = session.confirm_slot_as_planned(request.slot_position)
            await repos.sessions.save(session)
            user.clear_expectation()
            await repos.users.save(user)
            return cmds.ConfirmExerciseAsPlannedCommandResult(
                session_id=session.id,
                slot=slot,
                document=session.to_document(),
            )


class RecordSlotActualCommandHandler(
    cqrs.RequestHandler[cmds.RecordSlotActualCommand, cmds.RecordSlotActualCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.RecordSlotActualCommand) -> cmds.RecordSlotActualCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_session_id is None:
                raise DomainError("open session is required")
            session = await repos.sessions.get_by_id(user.active_session_id)
            if session is None or session.status != SessionStatus.IN_PROGRESS:
                raise DomainError("slot actual can be recorded only while in_progress")

            actual = SlotActual(
                sets=request.sets,
                reps=request.reps,
                duration_seconds=request.duration_seconds,
                weight_kg=request.weight_kg,
                note=request.note,
            )
            slot = session.apply_slot_actual(request.slot_position, actual)
            await repos.sessions.save(session)
            user.clear_expectation()
            await repos.users.save(user)
            return cmds.RecordSlotActualCommandResult(
                session_id=session.id,
                slot=slot,
                document=session.to_document(),
            )


class ProposeSlotActualCommandHandler(
    cqrs.RequestHandler[cmds.ProposeSlotActualCommand, cmds.ProposeSlotActualCommandResult],
):
    def __init__(self, uow: IUow, language_model: LanguageModel) -> None:
        self._uow = uow
        self._language_model = language_model

    async def handle(self, request: cmds.ProposeSlotActualCommand) -> cmds.ProposeSlotActualCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_session_id is None:
                raise DomainError("open session is required")
            session = await repos.sessions.get_by_id(user.active_session_id)
            if session is None or session.status != SessionStatus.IN_PROGRESS:
                raise DomainError("slot actual can be proposed only while in_progress")

            slot_position = request.slot_position if request.slot_position is not None else user.focus_slot
            if slot_position is None:
                raise DomainError("focus_slot is required for slot actual")

            pending = await repos.proposals.get_pending_for_user(user.id)
            if (
                pending is not None
                and pending.kind == ProposalKind.PERFORMANCE
                and pending.base_session_id == session.id
                and pending.document is not None
            ):
                current = pending.document
            else:
                current = session.to_document()

            day = current.days[0]
            planned = next((slot for slot in day.slots if slot.position == slot_position), None)
            if planned is None:
                raise InvalidWorkoutDocument(f"slot position={slot_position} not found")

            try:
                payload = await complete_json(
                    self._language_model,
                    prompt_name="performance_parser.md",
                    prompt_context={
                        "slot_json": slot_json(planned),
                        "utterance": request.utterance,
                    },
                )
            except AgentUnavailable:
                return cmds.ProposeSlotActualCommandResult(agent_unavailable=True)

            try:
                slot_raw = payload.get("slot")
                if not isinstance(slot_raw, dict):
                    raise InvalidWorkoutDocument("response.slot must be an object")
                parsed = parse_slot(slot_raw)
                if parsed.actual is None:
                    raise InvalidWorkoutDocument("response.slot.actual is required")
                # Keep planned fields from the current document; only accept actual from the model.
                updated_slot = planned.with_actual(parsed.actual)
                slots = [updated_slot if slot.position == slot_position else slot for slot in day.slots]
                document = current.model_copy(
                    update={"days": [day.model_copy(update={"slots": slots})]},
                )
                reply = clip_reply(payload.get("reply"))
            except (InvalidWorkoutDocument, ValueError, TypeError, KeyError):
                return cmds.ProposeSlotActualCommandResult(
                    schema_failed=True,
                    reply=reply_from_payload(payload),
                )

            if (
                pending is not None
                and pending.kind == ProposalKind.PERFORMANCE
                and pending.base_session_id == session.id
            ):
                pending.replace_document(document, reply=reply)
                saved = await repos.proposals.save(pending)
            else:
                proposal = Proposal.new_performance(
                    user_id=user.id,
                    document=document,
                    base_session_id=session.id,
                    reply=reply,
                )
                saved = await _replace_pending(repos, user, proposal)

            user.expect_input(
                ExpectedInput.PROPOSAL_UTTERANCE,
                expected_field="slot_actual",
                focus_slot=slot_position,
            )
            user.pending_proposal_id = saved.id
            await repos.users.save(user)
            return cmds.ProposeSlotActualCommandResult(
                proposal_id=saved.id,
                reply=reply,
                document=document,
                slot_position=slot_position,
            )


class BeginSessionCompletionCommandHandler(
    cqrs.RequestHandler[cmds.BeginSessionCompletionCommand, cmds.BeginSessionCompletionCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.BeginSessionCompletionCommand,
    ) -> cmds.BeginSessionCompletionCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_session_id is None:
                raise DomainError("open session is required")
            session = await repos.sessions.get_by_id(user.active_session_id)
            if session is None or not session.is_open:
                raise DomainError("open session is required")
            session.begin_completion()
            await repos.sessions.save(session)
            user.expect_input(ExpectedInput.COMPLETION_DEVIATION)
            await repos.users.save(user)
            return cmds.BeginSessionCompletionCommandResult(
                session_id=session.id,
                document=session.to_document(),
                session_status=session.status,
            )


class RestartOpenSessionCommandHandler(
    cqrs.RequestHandler[cmds.RestartOpenSessionCommand, cmds.RestartOpenSessionCommandResult],
):
    def __init__(self, uow: IUow, object_storage: ObjectStorage) -> None:
        self._uow = uow
        self._object_storage = object_storage

    async def handle(self, request: cmds.RestartOpenSessionCommand) -> cmds.RestartOpenSessionCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_session_id is None:
                raise DomainError("open session is required")
            session = await repos.sessions.get_by_id(user.active_session_id)
            if session is None or not session.is_open:
                raise DomainError("open session is required")

            videos = await repos.technique_videos.list_for_session(session.id)
            for video in videos:
                try:
                    await self._object_storage.delete(video.object_key)
                except KeyError:
                    pass
            await repos.technique_videos.delete_for_session(session.id)

            pending = await repos.proposals.get_pending_for_user(user.id)
            if pending is not None and pending.base_session_id == session.id:
                pending.discard()
                await repos.proposals.save(pending)
                user.pending_proposal_id = None

            session.clear_actuals()
            await repos.sessions.save(session)
            user.clear_expectation()
            await repos.users.save(user)
            return cmds.RestartOpenSessionCommandResult(
                session_id=session.id,
                document=session.to_document(),
                session_status=session.status,
            )


class ProposeSessionDeviationCommandHandler(
    cqrs.RequestHandler[cmds.ProposeSessionDeviationCommand, cmds.ProposeSessionDeviationCommandResult],
):
    def __init__(self, uow: IUow, language_model: LanguageModel, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._language_model = language_model
        self._catalog = catalog

    async def handle(
        self,
        request: cmds.ProposeSessionDeviationCommand,
    ) -> cmds.ProposeSessionDeviationCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_session_id is None:
                raise DomainError("open session is required")
            session = await repos.sessions.get_by_id(user.active_session_id)
            if session is None or session.status != SessionStatus.PENDING_COMPLETION:
                raise DomainError("session must be pending_completion to record deviations")

            pending = await repos.proposals.get_pending_for_user(user.id)
            if (
                pending is not None
                and pending.kind == ProposalKind.COMPLETION_DEVIATION
                and pending.base_session_id == session.id
                and pending.document is not None
            ):
                current = pending.document
            else:
                current = session.to_document()

            records, allowed = await _load_catalog_ids(self._catalog)
            payload = None
            try:
                payload = await complete_json(
                    self._language_model,
                    prompt_name="workout_editor.md",
                    prompt_context={
                        "document_json": document_json(current),
                        "utterance": request.utterance,
                        "limitations": user.limitations or "",
                        "catalog_json": catalog_json(records),
                        "schema_json": workout_document_schema_json(),
                        "focus_day_position": current.days[0].position if current.days else 1,
                    },
                )
            except AgentUnavailable:
                return cmds.ProposeSessionDeviationCommandResult(agent_unavailable=True)

            try:
                document_raw = payload.get("document")
                if not isinstance(document_raw, dict):
                    raise InvalidWorkoutDocument("response.document must be an object")
                document = parse_workout_document(document_raw, default_program_type=session.program_type)
                document = document.model_copy(update={"program_type": session.program_type})
                if len(document.days) != 1:
                    raise InvalidWorkoutDocument("completion deviation requires exactly one day")
                document.assert_catalog_ids(allowed)
                reply = clip_reply(payload.get("reply"))
            except (InvalidWorkoutDocument, ValueError, TypeError, KeyError):
                return cmds.ProposeSessionDeviationCommandResult(
                    schema_failed=True,
                    reply=reply_from_payload(payload),
                )

            if (
                pending is not None
                and pending.kind == ProposalKind.COMPLETION_DEVIATION
                and pending.base_session_id == session.id
            ):
                pending.replace_document(document, reply=reply)
                saved = await repos.proposals.save(pending)
            else:
                proposal = Proposal.new_completion_deviation(
                    user_id=user.id,
                    document=document,
                    base_session_id=session.id,
                    reply=reply,
                )
                saved = await _replace_pending(repos, user, proposal)

            user.expect_input(ExpectedInput.COMPLETION_DEVIATION)
            user.pending_proposal_id = saved.id
            await repos.users.save(user)
            return cmds.ProposeSessionDeviationCommandResult(
                proposal_id=saved.id,
                reply=reply,
                document=document,
            )


class FinalizeSessionCommandHandler(
    cqrs.RequestHandler[cmds.FinalizeSessionCommand, cmds.FinalizeSessionCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.FinalizeSessionCommand) -> cmds.FinalizeSessionCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_session_id is None:
                raise DomainError("open session is required")
            session = await repos.sessions.get_by_id(user.active_session_id)
            if session is None or not session.is_open:
                raise DomainError("open session is required")
            session.finalize(now=datetime.now(UTC))
            await repos.sessions.save(session)

            pending = await repos.proposals.get_pending_for_user(user.id)
            if pending is not None and pending.base_session_id == session.id:
                pending.discard()
                await repos.proposals.save(pending)

            user.active_session_id = None
            user.pending_proposal_id = None
            user.clear_expectation()
            await repos.users.save(user)
            return cmds.FinalizeSessionCommandResult(
                session_id=session.id,
                document=session.to_document(),
                session_status=session.status,
            )


class GenerateNextSessionCommandHandler(
    cqrs.RequestHandler[cmds.GenerateNextSessionCommand, cmds.GenerateNextSessionCommandResult],
):
    def __init__(self, uow: IUow, language_model: LanguageModel, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._language_model = language_model
        self._catalog = catalog

    async def handle(self, request: cmds.GenerateNextSessionCommand) -> cmds.GenerateNextSessionCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_session_id is not None:
                existing = await repos.sessions.get_by_id(user.active_session_id)
                if existing is not None and existing.is_open:
                    raise DomainError("an open session already exists")
            if user.active_program_id is None:
                raise DomainError("active program is required to generate a session")
            if user.goal is None:
                raise DomainError("goal is required to generate a session")
            program = await repos.programs.get_by_id(user.active_program_id)
            if program is None:
                raise DomainError("active program not found")

            today = local_calendar_date(now=datetime.now(UTC), timezone_offset=user.timezone_offset)
            weekday = today.isoweekday()
            template = next((day for day in program.days if day.weekday == weekday), None)
            if template is None:
                raise DomainError("today is not a training day in the active program")

            weight = await repos.weights.latest_for_user(user.id)
            history = await repos.sessions.list_completed_for_user(user.id, limit=10)
            records, allowed = await _load_catalog_ids(self._catalog)
            if not records:
                raise DomainError("exercise catalog is empty")

            import json

            from fitness_bot.service.handlers.commands.program import build_profile_payload

            template_document = WorkoutDocument(
                program_type=program.program_type,
                days=[template],
            )
            history_payload = [
                {
                    "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                    "document": session.to_document().model_dump(mode="json"),
                }
                for session in history
            ]

            try:
                payload = await complete_json(
                    self._language_model,
                    prompt_name="next_session_planner.md",
                    prompt_context={
                        "template_json": document_json(template_document),
                        "history_json": json.dumps(history_payload, ensure_ascii=False),
                        "profile_json": json.dumps(
                            await build_profile_payload(
                                repos,
                                user,
                                weight_kg=weight.kilograms if weight else None,
                            ),
                            ensure_ascii=False,
                        ),
                        "goal": user.goal.value,
                        "catalog_json": catalog_json(records),
                    },
                )
            except AgentUnavailable:
                return cmds.GenerateNextSessionCommandResult(agent_unavailable=True)

            try:
                document_raw = payload.get("document")
                if not isinstance(document_raw, dict):
                    raise InvalidWorkoutDocument("response.document must be an object")
                document = parse_workout_document(document_raw, default_program_type=program.program_type)
                document = document.model_copy(update={"program_type": program.program_type})
                if len(document.days) != 1:
                    raise InvalidWorkoutDocument("next session requires exactly one day")
                # Keep template weekday/title when the model omits them.
                day = document.days[0]
                document = document.model_copy(
                    update={
                        "days": [
                            day.model_copy(
                                update={
                                    "weekday": day.weekday if day.weekday is not None else template.weekday,
                                    "title": day.title or template.title,
                                    "position": day.position or template.position,
                                },
                            ),
                        ],
                    },
                )
                document.assert_catalog_ids(allowed)
                reply = clip_reply(payload.get("reply"))
            except (InvalidWorkoutDocument, ValueError, TypeError, KeyError):
                return cmds.GenerateNextSessionCommandResult(
                    schema_failed=True,
                    reply=reply_from_payload(payload),
                )

            proposal = Proposal.new_next_session(
                user_id=user.id,
                document=document,
                base_program_id=program.id,
                reply=reply,
            )
            saved = await _replace_pending(repos, user, proposal)
            user.clear_expectation()
            user.pending_proposal_id = saved.id
            await repos.users.save(user)
            return cmds.GenerateNextSessionCommandResult(
                proposal_id=saved.id,
                reply=reply,
                document=document,
            )


class SaveTechniqueVideoCommandHandler(
    cqrs.RequestHandler[cmds.SaveTechniqueVideoCommand, cmds.SaveTechniqueVideoCommandResult],
):
    def __init__(self, uow: IUow, object_storage: ObjectStorage) -> None:
        self._uow = uow
        self._object_storage = object_storage

    async def handle(self, request: cmds.SaveTechniqueVideoCommand) -> cmds.SaveTechniqueVideoCommandResult:
        content_type = (request.content_type or "").strip().lower()
        if not content_type.startswith("video/"):
            raise DomainError("technique video must be a video/* file")
        byte_size = len(request.body)
        if byte_size <= 0 or byte_size > MAX_TECHNIQUE_VIDEO_BYTES:
            raise DomainError("technique video size must be between 1 and 20 MiB")

        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_session_id is None:
                raise DomainError("open session is required")
            session = await repos.sessions.get_by_id(user.active_session_id)
            if session is None or session.status not in {
                SessionStatus.IN_PROGRESS,
                SessionStatus.PENDING_COMPLETION,
            }:
                raise DomainError("technique video can be saved only while session is open")

            slot_position = request.slot_position if request.slot_position is not None else user.focus_slot
            if slot_position is None:
                raise DomainError("focus_slot is required for technique video")
            slot = session.slot_at(slot_position)
            if slot.actual is None:
                raise DomainError("slot actual is required before technique video")
            if slot.id is None:
                raise DomainError("slot id is required for technique video")

            existing = await repos.technique_videos.get_by_slot_id(slot.id)
            replaced = existing is not None
            if existing is not None:
                video = existing.replace_file(content_type=content_type, byte_size=byte_size)
                await self._object_storage.delete(existing.object_key)
            else:
                video = TechniqueVideo.create(
                    slot_id=slot.id,
                    user_id=user.id,
                    session_id=session.id,
                    content_type=content_type,
                    byte_size=byte_size,
                )

            await self._object_storage.put(video.object_key, request.body, content_type)
            await repos.technique_videos.upsert(video)
            user.clear_expectation()
            await repos.users.save(user)
            coach_chat_id = None
            coach_user_id = None
            link = await repos.coaches.get_active_link(client_user_id=user.id)
            if link is not None:
                coach = await repos.users.get_by_id(link.coach_user_id)
                if coach is not None:
                    coach_chat_id = coach.chat_id
                    coach_user_id = coach.id
            return cmds.SaveTechniqueVideoCommandResult(
                session_id=session.id,
                slot_id=slot.id,
                slot_position=slot_position,
                object_key=video.object_key,
                replaced=replaced,
                document=session.to_document(),
                coach_chat_id=coach_chat_id,
                coach_user_id=coach_user_id,
            )


class RememberTechniqueVideoFileIdCommandHandler(
    cqrs.RequestHandler[
        cmds.RememberTechniqueVideoFileIdCommand,
        cmds.RememberTechniqueVideoFileIdCommandResult,
    ],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.RememberTechniqueVideoFileIdCommand,
    ) -> cmds.RememberTechniqueVideoFileIdCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            video = await repos.technique_videos.get_by_slot_id(request.slot_id)
            if video is None or video.user_id != user.id:
                raise DomainError("technique video not found")
            updated = video.remember_telegram_file_id(request.telegram_file_id)
            await repos.technique_videos.upsert(updated)
            return cmds.RememberTechniqueVideoFileIdCommandResult(
                slot_id=updated.slot_id,
                telegram_file_id=updated.telegram_file_id or request.telegram_file_id,
            )
