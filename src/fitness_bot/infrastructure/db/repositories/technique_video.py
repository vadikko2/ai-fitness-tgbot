from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fitness_bot.domain.workout.technique_video import TechniqueVideo
from fitness_bot.infrastructure.db.models import TechniqueVideoRow
from fitness_bot.service.interfaces.uow import ITechniqueVideosRepository


def _to_domain(row: TechniqueVideoRow) -> TechniqueVideo:
    return TechniqueVideo(
        slot_id=row.slot_id,
        user_id=row.user_id,
        session_id=row.session_id,
        object_key=row.object_key,
        content_type=row.content_type,
        byte_size=row.byte_size,
        telegram_file_id=row.telegram_file_id,
        created_at=row.created_at,
    )


class SqlAlchemyTechniqueVideosRepository(ITechniqueVideosRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_slot_id(self, slot_id: UUID) -> TechniqueVideo | None:
        result = await self._session.execute(
            select(TechniqueVideoRow).where(TechniqueVideoRow.slot_id == slot_id),
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row else None

    async def list_for_session(self, session_id: UUID) -> list[TechniqueVideo]:
        result = await self._session.execute(
            select(TechniqueVideoRow).where(TechniqueVideoRow.session_id == session_id),
        )
        return [_to_domain(row) for row in result.scalars().all()]

    async def delete_for_session(self, session_id: UUID) -> None:
        await self._session.execute(
            delete(TechniqueVideoRow).where(TechniqueVideoRow.session_id == session_id),
        )
        await self._session.flush()

    async def upsert(self, video: TechniqueVideo) -> TechniqueVideo:
        result = await self._session.execute(
            select(TechniqueVideoRow).where(TechniqueVideoRow.slot_id == video.slot_id),
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = TechniqueVideoRow(
                slot_id=video.slot_id,
                user_id=video.user_id,
                session_id=video.session_id,
                object_key=video.object_key,
                content_type=video.content_type,
                byte_size=video.byte_size,
                telegram_file_id=video.telegram_file_id,
                created_at=video.created_at,
            )
            self._session.add(row)
        else:
            row.user_id = video.user_id
            row.session_id = video.session_id
            row.object_key = video.object_key
            row.content_type = video.content_type
            row.byte_size = video.byte_size
            row.telegram_file_id = video.telegram_file_id
            row.created_at = video.created_at
        await self._session.flush()
        return _to_domain(row)
