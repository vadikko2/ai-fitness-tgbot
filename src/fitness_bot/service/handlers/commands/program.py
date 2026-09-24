from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import cqrs

from fitness_bot.domain.enums import ExpectedInput, ProfileField, ProgramStatus, ProposalKind
from fitness_bot.domain.errors import (
    AgentUnavailable,
    DomainError,
    EmptyProgramWeek,
    InvalidWorkoutDocument,
    UnresolvedExercises,
)
from fitness_bot.domain.program_catalog import (
    planner_program_type_hint,
    planner_training_styles_guide,
    program_type_label,
)
from fitness_bot.domain.users.user import User
from fitness_bot.domain.workout.document import WorkoutDay, WorkoutDocument
from fitness_bot.domain.workout.program import Program
from fitness_bot.domain.workout.proposal import Proposal
from fitness_bot.domain.workout.session import Session
from fitness_bot.domain.workout.week_progress import training_week_progress
from fitness_bot.service.handlers.commands.agent_json import (
    catalog_json,
    clip_reply,
    complete_json,
    document_json,
    parse_workout_document,
    reply_from_payload,
    workout_document_schema_json,
)
from fitness_bot.service.interfaces.uow import IUow, IUowRepositories
from fitness_bot.service.models.commands import program as cmds
from fitness_bot.service.ports.language_model import LanguageModel
from fitness_bot.service.ports.video_search import CatalogExerciseRecord, ExerciseCatalogReader

logger = logging.getLogger(__name__)


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


def _profile_payload(
    user: User,
    *,
    weight_kg: object | None,
    circumferences_cm: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sex": user.sex.value if user.sex else None,
        "birth_year": user.birth_year,
        "age": user.age(),
        "height_cm": str(user.height_cm) if user.height_cm is not None else None,
        "weight_kg": str(weight_kg) if weight_kg is not None else None,
        "experience": user.experience.value if user.experience else None,
        "experience_details": user.experience_details,
        "days_per_week": user.days_per_week,
        "training_weekdays": sorted(user.training_weekdays),
        "equipment": user.equipment,
        "limitations": user.limitations,
        "activity_level": user.activity_level.value if user.activity_level else None,
        "session_minutes": user.session_minutes,
        "body_fat_pct": str(user.body_fat_pct) if user.body_fat_pct is not None else None,
        "body_fat_unknown": bool(user.body_fat_set and user.body_fat_pct is None),
        "supplements": sorted(user.supplements) if user.supplements is not None else None,
        "supplements_other": user.supplements_other,
        "diet_prefs": user.diet_prefs,
        "goal": user.goal.value if user.goal else None,
        "circumferences_cm": circumferences_cm or {},
    }
    if user.pharma is not None:
        payload["pharma"] = user.pharma
    return payload


async def _latest_circumferences(repos: IUowRepositories, user_id: UUID) -> dict[str, str]:
    sites = await repos.measurements.list_sites_for_user(user_id)
    site_by_id = {site.id: site for site in sites}
    history = await repos.measurements.history_for_user(user_id, limit=200)
    latest: dict[str, str] = {}
    for entry in history:
        site = site_by_id.get(entry.site_id)
        if site is None:
            continue
        key = site.code
        if key in latest:
            continue
        latest[key] = str(entry.centimeters)
    return latest


async def build_profile_payload(
    repos: IUowRepositories,
    user: User,
    *,
    weight_kg: object | None,
) -> dict[str, Any]:
    return _profile_payload(
        user,
        weight_kg=weight_kg,
        circumferences_cm=await _latest_circumferences(repos, user.id),
    )


async def _replace_pending(
    repos: IUowRepositories,
    user: User,
    proposal: Proposal,
) -> Proposal:
    previous = await repos.proposals.get_pending_for_user(user.id)
    if previous is not None and previous.id != proposal.id:
        previous.discard()
        await repos.proposals.save(previous)
    saved = await repos.proposals.save(proposal)
    user.pending_proposal_id = saved.id
    await repos.users.save(user)
    return saved


async def _load_catalog_ids(catalog: ExerciseCatalogReader) -> tuple[list[CatalogExerciseRecord], set[UUID]]:
    records = list(await catalog.list_exercises())
    return records, {record.id for record in records}


class ChooseProgramTypeCommandHandler(
    cqrs.RequestHandler[cmds.ChooseProgramTypeCommand, cmds.ChooseProgramTypeCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.ChooseProgramTypeCommand) -> cmds.ChooseProgramTypeCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            proposal = Proposal.new_program_type(user_id=user.id, program_type=request.program_type)
            saved = await _replace_pending(repos, user, proposal)
            user.expect_input(ExpectedInput.PROPOSAL_UTTERANCE, expected_field="program_edit")
            await repos.users.save(user)
            return cmds.ChooseProgramTypeCommandResult(
                proposal_id=saved.id,
                program_type=saved.program_type or request.program_type,
            )


class ProposeProgramCommandHandler(
    cqrs.RequestHandler[cmds.ProposeProgramCommand, cmds.ProposeProgramCommandResult],
):
    def __init__(self, uow: IUow, language_model: LanguageModel, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._language_model = language_model
        self._catalog = catalog

    async def handle(self, request: cmds.ProposeProgramCommand) -> cmds.ProposeProgramCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            pending = await repos.proposals.get_pending_for_user(user.id)
            if pending is None or pending.kind != ProposalKind.PROGRAM or pending.program_type is None:
                raise DomainError("choose program type before proposing a week")
            if user.days_per_week is None or user.goal is None:
                raise DomainError("profile must include days_per_week and goal")
            program_type = pending.program_type
            weight = await repos.weights.latest_for_user(user.id)
            records, allowed = await _load_catalog_ids(self._catalog)
            if not records:
                raise DomainError("exercise catalog is empty")

            import json

            profile_json = json.dumps(
                await build_profile_payload(
                    repos,
                    user,
                    weight_kg=weight.kilograms if weight else None,
                ),
                ensure_ascii=False,
            )
            payload: dict[str, Any] | None = None
            try:
                payload = await complete_json(
                    self._language_model,
                    prompt_name="program_planner.md",
                    prompt_context={
                        "profile_json": profile_json,
                        "goal": user.goal.value,
                        "weekdays_json": json.dumps(sorted(user.training_weekdays), ensure_ascii=False),
                        "days_per_week": user.days_per_week,
                        "program_type": program_type.value,
                        "program_type_label": program_type_label(program_type),
                        "program_type_hint": planner_program_type_hint(program_type),
                        "training_styles_guide": planner_training_styles_guide(),
                        "catalog_json": catalog_json(records),
                        "schema_json": workout_document_schema_json(),
                    },
                )
            except AgentUnavailable:
                return cmds.ProposeProgramCommandResult(agent_unavailable=True)
            except InvalidWorkoutDocument as exc:
                logger.warning("propose_program json failed: %s", exc)
                return cmds.ProposeProgramCommandResult(schema_failed=True)

            try:
                program_raw = payload.get("program")
                if not isinstance(program_raw, dict):
                    raise InvalidWorkoutDocument("response.program must be an object")
                if "program_type" not in program_raw:
                    program_raw = {**program_raw, "program_type": program_type.value}
                document = parse_workout_document(program_raw, default_program_type=program_type)
                document = document.model_copy(update={"program_type": program_type})
                document = document.with_unknown_ids_unresolved(allowed)
                document.assert_catalog_ids(allowed)
                document.assert_schedule_complete(days_per_week=user.days_per_week)
                reply = clip_reply(payload.get("reply"))
            except (InvalidWorkoutDocument, ValueError, TypeError, KeyError) as exc:
                logger.warning("propose_program schema failed: %s", exc)
                return cmds.ProposeProgramCommandResult(
                    schema_failed=True,
                    reply=reply_from_payload(payload),
                )

            pending.replace_document(document, reply=reply)
            if pending.base_program_id is None and user.active_program_id is not None:
                pending.base_program_id = user.active_program_id
            user.expect_input(ExpectedInput.PROPOSAL_UTTERANCE, expected_field="program_edit")
            saved = await repos.proposals.save(pending)
            user.pending_proposal_id = saved.id
            await repos.users.save(user)
            return cmds.ProposeProgramCommandResult(
                proposal_id=saved.id,
                reply=reply,
                document=document,
            )


class ProposeProgramChangeCommandHandler(
    cqrs.RequestHandler[cmds.ProposeProgramChangeCommand, cmds.ProposeProgramChangeCommandResult],
):
    def __init__(self, uow: IUow, language_model: LanguageModel, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._language_model = language_model
        self._catalog = catalog

    async def handle(self, request: cmds.ProposeProgramChangeCommand) -> cmds.ProposeProgramChangeCommandResult:
        from fitness_bot.service.authz import require_coach_of

        async with self._uow.transaction() as repos:
            actor = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            coach_actor = None
            if request.subject_user_id is not None:
                await require_coach_of(repos, actor, request.subject_user_id)
                user = _require_user(await repos.users.get_by_id(request.subject_user_id))
                coach_actor = actor
            else:
                user = actor
            pending = await repos.proposals.get_pending_for_user(user.id)
            if pending is None or pending.kind != ProposalKind.PROGRAM or pending.program_type is None:
                raise DomainError("choose program type before editing a week")
            program_type = pending.program_type
            if pending.document is not None:
                current = pending.document
            else:
                current = WorkoutDocument(
                    program_type=program_type,
                    days=[],
                )
            records, allowed = await _load_catalog_ids(self._catalog)

            focus_day_position = request.day_position
            focus_day: WorkoutDay | None = None
            editor_document = current
            if focus_day_position is not None:
                focus_day = next((day for day in current.days if day.position == focus_day_position), None)
                if focus_day is None:
                    raise DomainError(f"day position={focus_day_position} not found in draft")
                editor_document = WorkoutDocument(program_type=program_type, days=[focus_day])

            payload: dict[str, Any] | None = None
            try:
                payload = await complete_json(
                    self._language_model,
                    prompt_name="workout_editor.md",
                    prompt_context={
                        "document_json": document_json(editor_document),
                        "utterance": request.utterance,
                        "limitations": user.limitations or "",
                        "catalog_json": catalog_json(records),
                        "schema_json": workout_document_schema_json(),
                        "focus_day_position": focus_day_position,
                    },
                )
            except AgentUnavailable:
                return cmds.ProposeProgramChangeCommandResult(agent_unavailable=True)
            except InvalidWorkoutDocument:
                return cmds.ProposeProgramChangeCommandResult(schema_failed=True)

            try:
                document_raw = payload.get("document")
                if not isinstance(document_raw, dict):
                    raise InvalidWorkoutDocument("response.document must be an object")
                document = parse_workout_document(document_raw, default_program_type=program_type)
                document = document.model_copy(update={"program_type": program_type})
                if focus_day is not None and focus_day_position is not None:
                    if len(document.days) != 1:
                        raise InvalidWorkoutDocument("day edit requires exactly one day")
                    edited = document.days[0].model_copy(
                        update={
                            "position": focus_day_position,
                            "weekday": document.days[0].weekday or focus_day.weekday,
                        },
                    )
                    document = current.replace_day(edited)
                document = document.with_unknown_ids_unresolved(allowed)
                document.assert_catalog_ids(allowed)
                document.assert_schedule_complete()
                reply = clip_reply(payload.get("reply"))
            except (InvalidWorkoutDocument, ValueError, TypeError, KeyError):
                return cmds.ProposeProgramChangeCommandResult(
                    schema_failed=True,
                    reply=reply_from_payload(payload),
                )

            if pending.document is not None:
                pending.replace_document(document, reply=reply)
                saved = await repos.proposals.save(pending)
            else:
                proposal = Proposal.new_program_document(
                    user_id=user.id,
                    program_type=program_type,
                    document=document,
                    reply=reply,
                    base_program_id=user.active_program_id,
                )
                saved = await _replace_pending(repos, user, proposal)
            if coach_actor is not None:
                coach_actor.expect_input(
                    ExpectedInput.COACH_EDIT_CLIENT,
                    expected_field=str(user.id),
                )
                await repos.users.save(coach_actor)
            elif focus_day_position is not None:
                user.expect_input(
                    ExpectedInput.PROPOSAL_UTTERANCE,
                    expected_field="program_edit_day",
                    focus_slot=focus_day_position,
                )
                user.pending_proposal_id = saved.id
                await repos.users.save(user)
            else:
                user.expect_input(ExpectedInput.PROPOSAL_UTTERANCE, expected_field="program_edit")
                user.pending_proposal_id = saved.id
                await repos.users.save(user)
            return cmds.ProposeProgramChangeCommandResult(
                proposal_id=saved.id,
                reply=reply,
                document=document,
                day_position=focus_day_position,
                subject_user_id=request.subject_user_id,
            )


class SelectExerciseForProposalCommandHandler(
    cqrs.RequestHandler[cmds.SelectExerciseForProposalCommand, cmds.SelectExerciseForProposalCommandResult],
):
    def __init__(self, uow: IUow, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._catalog = catalog

    async def handle(
        self,
        request: cmds.SelectExerciseForProposalCommand,
    ) -> cmds.SelectExerciseForProposalCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            pending = await repos.proposals.get_pending_for_user(user.id)
            if pending is None or pending.document is None:
                raise DomainError("no pending proposal document")
            _, allowed = await _load_catalog_ids(self._catalog)
            if request.exercise_id not in allowed:
                raise DomainError("exercise_id is not in the catalog")
            document = pending.document.select_exercise(
                day_position=request.day_position,
                slot_position=request.slot_position,
                exercise_id=request.exercise_id,
            )
            pending.replace_document(document, reply=pending.reply)
            saved = await repos.proposals.save(pending)
            assert saved.document is not None
            return cmds.SelectExerciseForProposalCommandResult(
                proposal_id=saved.id,
                document=saved.document,
            )


class UpdateProposalSlotPlannedCommandHandler(
    cqrs.RequestHandler[cmds.UpdateProposalSlotPlannedCommand, cmds.UpdateProposalSlotPlannedCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.UpdateProposalSlotPlannedCommand,
    ) -> cmds.UpdateProposalSlotPlannedCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            pending = await repos.proposals.get_pending_for_user(user.id)
            if pending is None or pending.document is None:
                raise DomainError("no pending proposal document")
            try:
                document = pending.document.update_slot_planned(
                    day_position=request.day_position,
                    slot_position=request.slot_position,
                    weight_kg=request.weight_kg,
                    reps=request.reps,
                    duration_seconds=request.duration_seconds,
                )
            except InvalidWorkoutDocument as exc:
                raise DomainError(str(exc)) from exc
            pending.replace_document(document, reply=pending.reply)
            saved = await repos.proposals.save(pending)
            user.expect_input(ExpectedInput.NONE)
            await repos.users.save(user)
            assert saved.document is not None
            return cmds.UpdateProposalSlotPlannedCommandResult(
                proposal_id=saved.id,
                document=saved.document,
                day_position=request.day_position,
                slot_position=request.slot_position,
            )


class GenerateNextWeekCommandHandler(
    cqrs.RequestHandler[cmds.GenerateNextWeekCommand, cmds.GenerateNextWeekCommandResult],
):
    def __init__(self, uow: IUow, language_model: LanguageModel, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._language_model = language_model
        self._catalog = catalog

    async def handle(self, request: cmds.GenerateNextWeekCommand) -> cmds.GenerateNextWeekCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if user.active_session_id is not None:
                existing = await repos.sessions.get_by_id(user.active_session_id)
                if existing is not None and existing.is_open:
                    raise DomainError("an open session already exists")
            if user.active_program_id is None:
                raise DomainError("active program is required to generate a next week")
            if user.goal is None:
                raise DomainError("goal is required to generate a next week")
            program = await repos.programs.get_by_id(user.active_program_id)
            if program is None:
                raise DomainError("active program not found")

            weight = await repos.weights.latest_for_user(user.id)
            history = await repos.sessions.list_completed_for_user(user.id, limit=10)
            progress = training_week_progress(
                program,
                history,
                timezone_offset=user.timezone_offset,
                now=datetime.now(UTC),
            )
            records, allowed = await _load_catalog_ids(self._catalog)
            if not records:
                raise DomainError("exercise catalog is empty")

            import json

            history_payload = [
                {
                    "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                    "document": session.to_document().model_dump(mode="json"),
                }
                for session in history
            ]
            week_progress_payload = {
                "week_started_on": progress.week_started_on.isoformat() if progress.week_started_on else None,
                "planned_weekdays": progress.planned_weekdays,
                "completed_weekdays": progress.completed_weekdays,
                "week_finished": progress.week_finished,
            }

            payload: dict[str, Any] | None = None
            try:
                payload = await complete_json(
                    self._language_model,
                    prompt_name="next_week_planner.md",
                    prompt_context={
                        "program_json": document_json(program.to_document()),
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
                        "week_progress_json": json.dumps(week_progress_payload, ensure_ascii=False),
                        "catalog_json": catalog_json(records),
                        "schema_json": workout_document_schema_json(),
                    },
                )
            except AgentUnavailable:
                return cmds.GenerateNextWeekCommandResult(agent_unavailable=True)

            try:
                document_raw = payload.get("document")
                if not isinstance(document_raw, dict):
                    raise InvalidWorkoutDocument("response.document must be an object")
                document = parse_workout_document(document_raw, default_program_type=program.program_type)
                document = document.model_copy(update={"program_type": program.program_type})
                document = document.with_unknown_ids_unresolved(allowed)
                document.assert_catalog_ids(allowed)
                document.assert_schedule_complete(days_per_week=len(program.days) or None)
                reply = clip_reply(payload.get("reply"))
            except (InvalidWorkoutDocument, ValueError, TypeError, KeyError) as exc:
                logger.warning("generate_next_week schema failed: %s", exc)
                return cmds.GenerateNextWeekCommandResult(
                    schema_failed=True,
                    reply=reply_from_payload(payload),
                )

            proposal = Proposal.new_program_document(
                user_id=user.id,
                program_type=program.program_type,
                document=document,
                reply=reply,
                base_program_id=program.id,
            )
            saved = await _replace_pending(repos, user, proposal)
            user.expect_input(ExpectedInput.PROPOSAL_UTTERANCE, expected_field="program_edit")
            user.pending_proposal_id = saved.id
            await repos.users.save(user)
            return cmds.GenerateNextWeekCommandResult(
                proposal_id=saved.id,
                reply=reply,
                document=document,
            )


class ApproveProposalCommandHandler(
    cqrs.RequestHandler[cmds.ApproveProposalCommand, cmds.ApproveProposalCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.ApproveProposalCommand) -> cmds.ApproveProposalCommandResult:
        from fitness_bot.service.authz import require_coach_of

        async with self._uow.transaction() as repos:
            actor = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            coach_actor = None
            if request.subject_user_id is not None:
                await require_coach_of(repos, actor, request.subject_user_id)
                user = _require_user(await repos.users.get_by_id(request.subject_user_id))
                coach_actor = actor
            else:
                user = actor
            pending = await repos.proposals.get_pending_for_user(user.id)
            if pending is None:
                raise DomainError("no pending proposal")
            if pending.kind not in {
                ProposalKind.PROGRAM,
                ProposalKind.WORKOUT_EDIT,
                ProposalKind.PERFORMANCE,
                ProposalKind.COMPLETION_DEVIATION,
                ProposalKind.NEXT_SESSION,
            }:
                raise DomainError(f"approve does not support proposal kind {pending.kind.value}")
            if coach_actor is not None and pending.kind != ProposalKind.PROGRAM:
                raise DomainError("coach live-edit supports only program proposals")
            if pending.document is None:
                return cmds.ApproveProposalCommandResult(
                    proposal_id=pending.id,
                    blocked_empty=True,
                )
            try:
                document = pending.approve()
            except EmptyProgramWeek:
                return cmds.ApproveProposalCommandResult(
                    proposal_id=pending.id,
                    blocked_empty=True,
                    document=pending.document,
                )
            except UnresolvedExercises:
                return cmds.ApproveProposalCommandResult(
                    proposal_id=pending.id,
                    blocked_unresolved=True,
                    document=pending.document,
                )
            except InvalidWorkoutDocument:
                return cmds.ApproveProposalCommandResult(
                    proposal_id=pending.id,
                    blocked_schedule=True,
                    document=pending.document,
                )

            if pending.kind == ProposalKind.NEXT_SESSION:
                if user.active_session_id is not None:
                    existing = await repos.sessions.get_by_id(user.active_session_id)
                    if existing is not None and existing.is_open:
                        raise DomainError("an open session already exists")
                session = Session.from_document(user_id=user.id, document=document)
                saved_session = await repos.sessions.add(session)
                await repos.proposals.save(pending)
                user.active_session_id = saved_session.id
                user.pending_proposal_id = None
                user.clear_expectation()
                await repos.users.save(user)
                return cmds.ApproveProposalCommandResult(
                    session_id=saved_session.id,
                    proposal_id=pending.id,
                    document=document,
                )

            if pending.kind in {
                ProposalKind.WORKOUT_EDIT,
                ProposalKind.PERFORMANCE,
                ProposalKind.COMPLETION_DEVIATION,
            }:
                if pending.base_session_id is None:
                    raise DomainError(f"{pending.kind.value} proposal requires base_session_id")
                session = await repos.sessions.get_by_id(pending.base_session_id)
                if session is None or not session.is_open:
                    raise DomainError("open session not found for proposal")
                session.apply_document(document)
                await repos.sessions.save(session)
                await repos.proposals.save(pending)
                user.pending_proposal_id = None
                if pending.kind == ProposalKind.COMPLETION_DEVIATION:
                    user.expect_input(ExpectedInput.COMPLETION_DEVIATION)
                else:
                    user.clear_expectation()
                await repos.users.save(user)
                return cmds.ApproveProposalCommandResult(
                    session_id=session.id,
                    proposal_id=pending.id,
                    document=document,
                )

            now = datetime.now(UTC)
            if user.active_program_id is not None:
                current = await repos.programs.get_by_id(user.active_program_id)
                if current is not None and current.status.value == "active":
                    current.archive(now=now)
                    await repos.programs.save(current)

            # Persist program header first; days move from the proposal (SQL UPDATE / in-memory attach).
            program = Program(
                user_id=user.id,
                program_type=document.program_type,
                status=ProgramStatus.ACTIVE,
                days=[],
                created_at=now,
                activated_at=now,
            )
            saved_program = await repos.programs.add(program)
            await repos.proposals.save(pending)
            await repos.proposals.attach_days_to_program(pending.id, saved_program.id)
            reloaded = await repos.programs.get_by_id(saved_program.id)
            if reloaded is not None and reloaded.days:
                saved_program = reloaded
            else:
                saved_program.days = list(document.days)

            weekdays = [day.weekday for day in document.days if day.weekday is not None]
            user.apply_profile_field(ProfileField.DAYS_PER_WEEK, len(document.days))
            user.apply_profile_field(ProfileField.TRAINING_WEEKDAYS, weekdays)
            user.active_program_id = saved_program.id
            user.pending_proposal_id = None
            user.nutrition_stale = True
            await repos.nutrition.mark_all_stale_for_user(user.id)
            user.clear_expectation()
            await repos.users.save(user)
            if coach_actor is not None:
                coach_actor.clear_expectation()
                await repos.users.save(coach_actor)
            title = saved_program.display_title() if hasattr(saved_program, "display_title") else "План"
            return cmds.ApproveProposalCommandResult(
                program_id=saved_program.id,
                proposal_id=pending.id,
                nutrition_stale=True,
                document=document,
                client_chat_id=user.chat_id if coach_actor is not None else None,
                program_title=title if coach_actor is not None else None,
                subject_user_id=request.subject_user_id,
            )


class DiscardProposalCommandHandler(
    cqrs.RequestHandler[cmds.DiscardProposalCommand, cmds.DiscardProposalCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.DiscardProposalCommand) -> cmds.DiscardProposalCommandResult:
        from fitness_bot.service.authz import require_coach_of

        async with self._uow.transaction() as repos:
            actor = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            coach_actor = None
            if request.subject_user_id is not None:
                await require_coach_of(repos, actor, request.subject_user_id)
                user = _require_user(await repos.users.get_by_id(request.subject_user_id))
                coach_actor = actor
            else:
                user = actor
            pending = await repos.proposals.get_pending_for_user(user.id)
            if pending is None:
                raise DomainError("no pending proposal")
            pending.discard()
            await repos.proposals.save(pending)
            user.pending_proposal_id = None
            user.clear_expectation()
            await repos.users.save(user)
            if coach_actor is not None:
                coach_actor.clear_expectation()
                await repos.users.save(coach_actor)
            return cmds.DiscardProposalCommandResult(
                proposal_id=pending.id,
                subject_user_id=request.subject_user_id,
            )
