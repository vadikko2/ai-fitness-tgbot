from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fitness_bot.domain.enums import ProgramType, SessionStatus
from fitness_bot.domain.workout.document import SlotActual, WorkoutDocument
from fitness_bot.service.models.queries.base import Query, QueryResult


class GetTodayWorkoutQuery(Query):
    telegram_user_id: int


class GetTodayWorkoutQueryResult(QueryResult):
    screen: str
    session_id: UUID | None = None
    session_status: SessionStatus | None = None
    program_id: UUID | None = None
    program_type: ProgramType | None = None
    document: WorkoutDocument | None = None
    weekday: int | None = None
    week_started_on: date | None = None
    planned_weekdays: list[int] = []
    completed_weekdays: list[int] = []
    week_finished: bool = False
    technique_video_positions: list[int] = []
    has_unapplied_wellbeing: bool = False


class GetSessionHistoryQuery(Query):
    telegram_user_id: int
    offset: int = 0
    limit: int = 10
    subject_user_id: UUID | None = None


class SessionHistoryItem(QueryResult):
    session_id: UUID
    title: str
    completed_at: datetime | None = None


class GetSessionHistoryQueryResult(QueryResult):
    items: list[SessionHistoryItem]
    offset: int
    limit: int
    has_more: bool
    subject_user_id: UUID | None = None


class GetSessionDetailQuery(Query):
    telegram_user_id: int
    session_id: UUID
    subject_user_id: UUID | None = None


class SessionDetailSlot(QueryResult):
    slot_id: UUID
    position: int
    exercise_id: UUID | None = None
    exercise_name: str | None = None
    custom_request: str | None = None
    muscle_group: str | None = None
    actual: SlotActual | None = None
    has_technique_video: bool = False


class GetSessionDetailQueryResult(QueryResult):
    session_id: UUID
    title: str
    completed_at: datetime | None = None
    program_type: ProgramType
    slots: list[SessionDetailSlot]
    subject_user_id: UUID | None = None


class PrepareTechniqueVideoDeliveryQuery(Query):
    telegram_user_id: int
    slot_id: UUID
    subject_user_id: UUID | None = None


class PrepareTechniqueVideoDeliveryQueryResult(QueryResult):
    slot_id: UUID
    exercise_name: str
    telegram_file_id: str | None = None
    body: bytes | None = None
    content_type: str | None = None
    missing: bool = False


class ListClientRecentVideosQuery(Query):
    telegram_user_id: int
    client_user_id: UUID
    limit: int = 10


class ClientRecentVideoItem(QueryResult):
    slot_id: UUID
    session_id: UUID
    session_title: str
    exercise_name: str | None = None
    created_at: datetime


class ListClientRecentVideosQueryResult(QueryResult):
    items: list[ClientRecentVideoItem]
    client_user_id: UUID
    total_count: int = 0
