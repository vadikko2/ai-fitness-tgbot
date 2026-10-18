from __future__ import annotations

from datetime import UTC, datetime

import cqrs

from fitness_bot.domain.body.wellbeing import fresh_unapplied
from fitness_bot.domain.catalog.similar import similar_exercises
from fitness_bot.domain.enums import SessionStatus
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import User, local_calendar_date
from fitness_bot.domain.workout.document import WorkoutDocument
from fitness_bot.domain.workout.program import Program
from fitness_bot.domain.workout.week_progress import (
    TrainingWeekProgress,
    nearest_open_training_day,
    training_week_progress,
)
from fitness_bot.service.authz import require_coach_of
from fitness_bot.service.interfaces.uow import IUow, IUowRepositories
from fitness_bot.service.models.queries import session as queries
from fitness_bot.service.ports.object_storage import ObjectStorage
from fitness_bot.service.ports.video_search import ExerciseCatalogReader


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


def _progress_fields(progress: TrainingWeekProgress) -> dict:
    return {
        "week_started_on": progress.week_started_on,
        "planned_weekdays": progress.planned_weekdays,
        "completed_weekdays": progress.completed_weekdays,
        "week_finished": progress.week_finished,
    }


async def _week_progress_for_program(
    repos: IUowRepositories,
    *,
    user: User,
    program: Program,
) -> TrainingWeekProgress:
    history = await repos.sessions.list_completed_for_user(user.id, limit=50)
    return training_week_progress(
        program,
        history,
        timezone_offset=user.timezone_offset,
        now=datetime.now(UTC),
    )


class GetTodayWorkoutQueryHandler(
    cqrs.RequestHandler[queries.GetTodayWorkoutQuery, queries.GetTodayWorkoutQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetTodayWorkoutQuery) -> queries.GetTodayWorkoutQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            weekday = local_calendar_date(
                now=datetime.now(UTC),
                timezone_offset=user.timezone_offset,
            ).isoweekday()

            has_unapplied = bool(
                fresh_unapplied(
                    await repos.wellbeing.list_unapplied(user.id, limit=1),
                    now=datetime.now(UTC),
                ),
            )

            if user.active_session_id is not None:
                session = await repos.sessions.get_by_id(user.active_session_id)
                if session is not None and session.is_open:
                    videos = await repos.technique_videos.list_for_session(session.id)
                    video_slot_ids = {video.slot_id for video in videos}
                    positions = [
                        slot.position for slot in session.day.slots if slot.id is not None and slot.id in video_slot_ids
                    ]
                    return queries.GetTodayWorkoutQueryResult(
                        screen="session",
                        session_id=session.id,
                        session_status=session.status,
                        program_id=user.active_program_id,
                        program_type=session.program_type,
                        document=session.to_document(),
                        weekday=weekday,
                        technique_video_positions=positions,
                        has_unapplied_wellbeing=has_unapplied,
                    )

            if user.active_program_id is None:
                return queries.GetTodayWorkoutQueryResult(screen="no_program", weekday=weekday)

            program = await repos.programs.get_by_id(user.active_program_id)
            if program is None:
                return queries.GetTodayWorkoutQueryResult(screen="no_program", weekday=weekday)

            progress = await _week_progress_for_program(repos, user=user, program=program)
            template = next((day for day in program.days if day.weekday == weekday), None)
            if template is None:
                alternative = nearest_open_training_day(
                    program,
                    progress.completed_weekdays,
                    today_weekday=weekday,
                )
                return queries.GetTodayWorkoutQueryResult(
                    screen="rest",
                    program_id=program.id,
                    program_type=program.program_type,
                    weekday=weekday,
                    has_unapplied_wellbeing=has_unapplied,
                    alternative_weekday=alternative.weekday if alternative else None,
                    alternative_title=alternative.title if alternative else None,
                    **_progress_fields(progress),
                )

            document = WorkoutDocument(program_type=program.program_type, days=[template])
            return queries.GetTodayWorkoutQueryResult(
                screen="template",
                program_id=program.id,
                program_type=program.program_type,
                document=document,
                weekday=weekday,
                has_unapplied_wellbeing=has_unapplied,
                **_progress_fields(progress),
            )


class GetSimilarExercisesQueryHandler(
    cqrs.RequestHandler[queries.GetSimilarExercisesQuery, queries.GetSimilarExercisesQueryResult],
):
    def __init__(self, uow: IUow, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._catalog = catalog

    async def handle(self, request: queries.GetSimilarExercisesQuery) -> queries.GetSimilarExercisesQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            session = await repos.sessions.get_by_id(user.active_session_id) if user.active_session_id else None
        position = request.slot_position
        if session is None or session.status != SessionStatus.IN_PROGRESS:
            return queries.GetSimilarExercisesQueryResult(slot_position=position, blocked_reason="no_session")
        slot = next((item for item in session.day.slots if item.position == position), None)
        if slot is None or slot.exercise_id is None:
            return queries.GetSimilarExercisesQueryResult(slot_position=position, blocked_reason="unresolved")
        records = await self._catalog.list_exercises()
        target = next((record for record in records if record.id == slot.exercise_id), None)
        if target is None:
            return queries.GetSimilarExercisesQueryResult(slot_position=position, blocked_reason="unresolved")
        base = queries.GetSimilarExercisesQueryResult(
            slot_position=position,
            exercise_id=target.id,
            exercise_name=target.name,
            primary_muscles=list(target.primary_muscles),
            secondary_muscles=list(target.secondary_muscles),
            offset=max(0, request.offset),
        )
        if slot.actual is not None:
            return base.model_copy(update={"blocked_reason": "logged"})
        page = similar_exercises(
            target,
            records,
            training_place=user.training_place,
            exclude_ids={item.exercise_id for item in session.day.slots if item.exercise_id is not None},
            offset=request.offset,
            limit=max(1, min(request.limit, 10)),
        )
        by_id = {record.id: record for record in records}
        return base.model_copy(
            update={
                "items": [
                    queries.SimilarExerciseItem(
                        exercise_id=item.exercise_id,
                        name=item.name,
                        primary_muscles=list(by_id[item.exercise_id].primary_muscles),
                        secondary_muscles=list(by_id[item.exercise_id].secondary_muscles),
                    )
                    for item in page.items
                ],
                "has_more": page.has_more,
            },
        )


class GetSessionHistoryQueryHandler(
    cqrs.RequestHandler[queries.GetSessionHistoryQuery, queries.GetSessionHistoryQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetSessionHistoryQuery) -> queries.GetSessionHistoryQueryResult:
        offset = max(0, request.offset)
        limit = max(1, min(request.limit, 50))
        async with self._uow.transaction() as repos:
            actor = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if request.subject_user_id is not None:
                await require_coach_of(repos, actor, request.subject_user_id)
                user = _require_user(await repos.users.get_by_id(request.subject_user_id))
            else:
                user = actor
            items = await repos.sessions.list_completed_for_user(
                user.id,
                limit=limit + 1,
                offset=offset,
            )
            page = items[:limit]
            return queries.GetSessionHistoryQueryResult(
                items=[
                    queries.SessionHistoryItem(
                        session_id=session.id,
                        title=session.day.title,
                        completed_at=session.completed_at,
                    )
                    for session in page
                ],
                offset=offset,
                limit=limit,
                has_more=len(items) > limit,
                subject_user_id=request.subject_user_id,
            )


class GetSessionDetailQueryHandler(
    cqrs.RequestHandler[queries.GetSessionDetailQuery, queries.GetSessionDetailQueryResult],
):
    def __init__(self, uow: IUow, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._catalog = catalog

    async def handle(self, request: queries.GetSessionDetailQuery) -> queries.GetSessionDetailQueryResult:
        async with self._uow.transaction() as repos:
            actor = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if request.subject_user_id is not None:
                await require_coach_of(repos, actor, request.subject_user_id)
                user = _require_user(await repos.users.get_by_id(request.subject_user_id))
            else:
                user = actor
            session = await repos.sessions.get_by_id(request.session_id)
            if session is None or session.user_id != user.id:
                raise DomainError("session not found")
            if session.status != SessionStatus.COMPLETED:
                raise DomainError("only completed sessions are shown in history")

            videos = await repos.technique_videos.list_for_session(session.id)
            video_slot_ids = {video.slot_id for video in videos}
            records = await self._catalog.list_exercises()
            names = {record.id: record.name for record in records}

            slots: list[queries.SessionDetailSlot] = []
            for slot in session.day.slots:
                if slot.id is None:
                    continue
                slots.append(
                    queries.SessionDetailSlot(
                        slot_id=slot.id,
                        position=slot.position,
                        exercise_id=slot.exercise_id,
                        exercise_name=names.get(slot.exercise_id) if slot.exercise_id else None,
                        custom_request=slot.custom_request,
                        muscle_group=slot.muscle_group,
                        actual=slot.actual,
                        has_technique_video=slot.id in video_slot_ids,
                    ),
                )
            return queries.GetSessionDetailQueryResult(
                session_id=session.id,
                title=session.day.title,
                completed_at=session.completed_at,
                program_type=session.program_type,
                slots=slots,
                subject_user_id=request.subject_user_id,
            )


class PrepareTechniqueVideoDeliveryQueryHandler(
    cqrs.RequestHandler[
        queries.PrepareTechniqueVideoDeliveryQuery,
        queries.PrepareTechniqueVideoDeliveryQueryResult,
    ],
):
    def __init__(self, uow: IUow, object_storage: ObjectStorage, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._object_storage = object_storage
        self._catalog = catalog

    async def handle(
        self,
        request: queries.PrepareTechniqueVideoDeliveryQuery,
    ) -> queries.PrepareTechniqueVideoDeliveryQueryResult:
        async with self._uow.transaction() as repos:
            viewer = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            video = await repos.technique_videos.get_by_slot_id(request.slot_id)
            if video is None:
                return queries.PrepareTechniqueVideoDeliveryQueryResult(
                    slot_id=request.slot_id,
                    exercise_name="Упражнение",
                    missing=True,
                )
            owner_id = request.subject_user_id or video.user_id
            if video.user_id != owner_id:
                return queries.PrepareTechniqueVideoDeliveryQueryResult(
                    slot_id=request.slot_id,
                    exercise_name="Упражнение",
                    missing=True,
                )
            if viewer.id != video.user_id:
                await require_coach_of(repos, viewer, video.user_id)

            session = await repos.sessions.get_by_id(video.session_id)
            exercise_name = "Упражнение"
            if session is not None:
                slot = next((item for item in session.day.slots if item.id == video.slot_id), None)
                if slot is not None and slot.exercise_id is not None:
                    records = await self._catalog.list_exercises()
                    names = {record.id: record.name for record in records}
                    exercise_name = names.get(slot.exercise_id) or exercise_name
                elif slot is not None and slot.custom_request:
                    exercise_name = slot.custom_request

            # Prefer bytes for coach viewers (file_id is chat-bound to the athlete).
            if video.telegram_file_id and viewer.id == video.user_id:
                return queries.PrepareTechniqueVideoDeliveryQueryResult(
                    slot_id=video.slot_id,
                    exercise_name=exercise_name,
                    telegram_file_id=video.telegram_file_id,
                    content_type=video.content_type,
                )

            try:
                body = await self._object_storage.get(video.object_key)
            except KeyError:
                return queries.PrepareTechniqueVideoDeliveryQueryResult(
                    slot_id=video.slot_id,
                    exercise_name=exercise_name,
                    missing=True,
                )
            return queries.PrepareTechniqueVideoDeliveryQueryResult(
                slot_id=video.slot_id,
                exercise_name=exercise_name,
                body=body,
                content_type=video.content_type,
            )


class ListClientRecentVideosQueryHandler(
    cqrs.RequestHandler[queries.ListClientRecentVideosQuery, queries.ListClientRecentVideosQueryResult],
):
    def __init__(self, uow: IUow, catalog: ExerciseCatalogReader) -> None:
        self._uow = uow
        self._catalog = catalog

    async def handle(
        self,
        request: queries.ListClientRecentVideosQuery,
    ) -> queries.ListClientRecentVideosQueryResult:
        limit = max(1, min(request.limit, 30))
        async with self._uow.transaction() as repos:
            coach = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            await require_coach_of(repos, coach, request.client_user_id)
            sessions = await repos.sessions.list_completed_for_user(request.client_user_id, limit=40)
            records = await self._catalog.list_exercises()
            names = {record.id: record.name for record in records}
            items: list[queries.ClientRecentVideoItem] = []
            total = 0
            for session in sessions:
                videos = await repos.technique_videos.list_for_session(session.id)
                total += len(videos)
                for video in sorted(videos, key=lambda item: item.created_at, reverse=True):
                    if len(items) >= limit:
                        continue
                    slot = next((s for s in session.day.slots if s.id == video.slot_id), None)
                    exercise_name = None
                    if slot is not None:
                        if slot.exercise_id is not None:
                            exercise_name = names.get(slot.exercise_id)
                        elif slot.custom_request:
                            exercise_name = slot.custom_request
                    items.append(
                        queries.ClientRecentVideoItem(
                            slot_id=video.slot_id,
                            session_id=session.id,
                            session_title=session.day.title,
                            exercise_name=exercise_name,
                            created_at=video.created_at,
                        ),
                    )
            return queries.ListClientRecentVideosQueryResult(
                items=items,
                client_user_id=request.client_user_id,
                total_count=total,
            )
